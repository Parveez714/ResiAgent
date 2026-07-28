import os
import re
import csv
import json
import io
import tempfile
import requests
import pandas as pd
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from agno.agent import Agent
from agno.models.google import Gemini
from agno.tools.duckdb import DuckDbTools
from agno.tools.pandas import PandasTools

# Load env variables from root directory
load_dotenv(dotenv_path="../.env")
if not os.getenv("API_1_URL"):
    load_dotenv(dotenv_path=".env")

app = FastAPI(title="Project Analytics & AI Agent API")

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global caches
_cached_df1: Optional[pd.DataFrame] = None
_cached_df2: Optional[pd.DataFrame] = None
_cached_profile1: Optional[dict] = None
_cached_profile2: Optional[dict] = None

def json_to_df(json_data) -> pd.DataFrame:
    if isinstance(json_data, dict):
        if "data" in json_data and isinstance(json_data["data"], dict):
            inner_data = json_data["data"]
            for k, v in inner_data.items():
                if isinstance(v, list) and len(v) > 0:
                    return pd.DataFrame(v[0] if isinstance(v[0], list) else v)
        list_keys = [k for k, v in json_data.items() if isinstance(v, list) and len(v) > 0]
        if list_keys:
            target_list = json_data[list_keys[0]]
            return pd.DataFrame(target_list[0] if isinstance(target_list[0], list) else target_list)
        return pd.json_normalize(json_data)
    elif isinstance(json_data, list):
        return pd.DataFrame(json_data[0] if (len(json_data) > 0 and isinstance(json_data[0], list)) else json_data)
    return pd.json_normalize(json_data)

def coerce_column_types(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if "date" in col.lower() or "time" in col.lower():
            df[col] = pd.to_datetime(df[col], errors="coerce")
        elif df[col].dtype == "object":
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() / max(len(df), 1) > 0.9:
                df[col] = converted
    return df

def fetch_api_dataset(url_key, method_key, hkey_key, hval_key, payload_key) -> pd.DataFrame:
    url = os.getenv(url_key, "").strip()
    if not url:
        raise HTTPException(status_code=500, detail=f"{url_key} not configured in environment")

    method = os.getenv(method_key, "GET").strip().upper()
    hkey = os.getenv(hkey_key, "").strip()
    hval = os.getenv(hval_key, "").strip()
    payload_raw = os.getenv(payload_key, "").strip()

    headers = {"accept": "application/json, text/plain, */*"}
    if hkey and hval:
        headers[hkey] = hval

    kwargs = {"headers": headers, "timeout": 25}
    if payload_raw:
        headers["Content-Type"] = "application/json"
        try:
            kwargs["json"] = json.loads(payload_raw)
        except Exception:
            kwargs["data"] = payload_raw

    response = requests.request(method=method, url=url, **kwargs)
    response.raise_for_status()

    try:
        df = json_to_df(response.json())
    except Exception:
        df = pd.read_csv(io.StringIO(response.text))

    return coerce_column_types(df)

def fetch_data1() -> pd.DataFrame:
    global _cached_df1
    if _cached_df1 is not None:
        return _cached_df1
    _cached_df1 = fetch_api_dataset("API_1_URL", "API_1_METHOD", "API_1_HEADER_KEY", "API_1_HEADER_VALUE", "API_1_PAYLOAD")
    return _cached_df1

def fetch_data2() -> pd.DataFrame:
    global _cached_df2
    if _cached_df2 is not None:
        return _cached_df2
    try:
        _cached_df2 = fetch_api_dataset("API_2_URL", "API_2_METHOD", "API_2_HEADER_KEY", "API_2_HEADER_VALUE", "API_2_PAYLOAD")
    except Exception:
        # Fallback to empty dataframe if API 2 fails or is unconfigured
        _cached_df2 = pd.DataFrame()
    return _cached_df2

def profile_dataframe(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {}
    profile = {
        "row_count": len(df),
        "col_count": len(df.columns),
        "numeric_cols": [],
        "categorical_cols": [],
        "date_cols": [],
        "id_like_cols": [],
        "low_card_cols": [],
        "col_stats": {},
        "top_numeric_by_variance": [],
        "best_category_col": None,
        "best_value_col": None,
    }

    for col in df.columns:
        series = df[col].dropna()
        if series.empty:
            continue

        if pd.api.types.is_datetime64_any_dtype(df[col]):
            profile["date_cols"].append(col)
            profile["col_stats"][col] = {"min": str(series.min()), "max": str(series.max())}
        elif pd.api.types.is_numeric_dtype(df[col]):
            profile["numeric_cols"].append(col)
            profile["col_stats"][col] = {
                "min": float(series.min()),
                "max": float(series.max()),
                "mean": float(series.mean()),
                "sum": float(series.sum()),
                "nunique": int(series.nunique()),
            }
        else:
            nunique = series.nunique()
            profile["categorical_cols"].append(col)
            profile["col_stats"][col] = {
                "nunique": nunique,
                "top_values": series.value_counts().head(5).to_dict(),
            }
            if nunique > max(50, len(df) * 0.5):
                profile["id_like_cols"].append(col)
            else:
                profile["low_card_cols"].append(col)

    if profile["numeric_cols"]:
        ranked = sorted(
            profile["numeric_cols"],
            key=lambda c: df[c].std() if len(df) > 1 else 0.0,
            reverse=True
        )
        profile["top_numeric_by_variance"] = ranked
        money_hints = ["received", "revenue", "amount", "total", "receipt", "sales", "value", "realization", "invoiced"]
        for col in ranked:
            if any(h in col.lower() for h in money_hints):
                profile["best_value_col"] = col
                break
        if not profile["best_value_col"] and ranked:
            profile["best_value_col"] = ranked[0]

    name_hints = ["name", "project", "partner", "location", "type", "category"]
    cat_candidates = profile["low_card_cols"] + profile["id_like_cols"]
    for col in cat_candidates:
        if any(h in col.lower() for h in name_hints):
            profile["best_category_col"] = col
            break
    if not profile["best_category_col"] and cat_candidates:
        profile["best_category_col"] = cat_candidates[0]

    return profile

def get_profile1() -> dict:
    global _cached_profile1
    if _cached_profile1 is None:
        _cached_profile1 = profile_dataframe(fetch_data1())
    return _cached_profile1

def get_profile2() -> dict:
    global _cached_profile2
    if _cached_profile2 is None:
        _cached_profile2 = profile_dataframe(fetch_data2())
    return _cached_profile2

def save_df_to_temp_csv(df: pd.DataFrame) -> str:
    df_clean = df.copy()
    for col in df_clean.select_dtypes(include=["object"]):
        df_clean[col] = df_clean[col].astype(str).replace({r'"': '""'}, regex=True)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as f:
        df_clean.to_csv(f.name, index=False, quoting=csv.QUOTE_ALL)
        return f.name

def build_schema_summary(profile: dict, df: pd.DataFrame) -> str:
    if not profile:
        return "No data profile available."
    lines = [
        f"Rows: {profile.get('row_count', 0)} | Columns: {profile.get('col_count', 0)}",
        f"Numeric columns: {profile.get('numeric_cols', [])}",
        f"Categorical columns: {profile.get('categorical_cols', [])}",
        f"Date columns: {profile.get('date_cols', [])}",
        "Column statistics:"
    ]
    for col, stats in profile.get("col_stats", {}).items():
        lines.append(f"  {col}: {stats}")
    lines.append(f"\nSample records (first 3):")
    lines.append(df.head(3).to_string(index=False))
    return "\n".join(lines)

class KPIResponse(BaseModel):
    total_units: int
    sold: int
    unsold: int
    sold_value: float
    unsold_value: float
    invoiced: float
    uninvoiced: float
    received: float

@app.get("/api/projects")
def get_projects():
    df = fetch_data1()
    if "Project_Name" not in df.columns:
        return []
    projects = df["Project_Name"].dropna().unique().tolist()
    return sorted([str(p) for p in projects])

@app.get("/api/kpis", response_model=KPIResponse)
def get_kpis(projects: Optional[List[str]] = Query(None)):
    df = fetch_data1()
    if projects and len(projects) > 0 and "All" not in projects:
        df_filtered = df[df["Project_Name"].isin(projects)]
    else:
        df_filtered = df

    total_units = int(df_filtered['TotalInventory'].sum()) if 'TotalInventory' in df_filtered.columns else 0
    sold = int(df_filtered['SoldInventory'].sum()) if 'SoldInventory' in df_filtered.columns else 0
    unsold = int(df_filtered['AvailableInventory'].sum()) if 'AvailableInventory' in df_filtered.columns else 0
    sold_value = float(df_filtered['TotalSalesRealization'].sum()) if 'TotalSalesRealization' in df_filtered.columns else 0.0
    
    unsold_values = []
    for _, row in df_filtered.iterrows():
        avg_val = row.get('AverageUnitValue', 0)
        u_units = row.get('AvailableInventory', 0)
        if avg_val > 0:
            unsold_values.append(u_units * avg_val)
        else:
            avg_rate = row.get('AverageSaleRate', 0)
            u_area = row.get('AvailableArea', 0)
            unsold_values.append(u_area * avg_rate)
    unsold_value = float(sum(unsold_values))
    
    invoiced = float(df_filtered['TotalInvoiced'].sum()) if 'TotalInvoiced' in df_filtered.columns else 0.0
    uninvoiced = float(df_filtered['BalanceToBeInvoiced'].sum()) if 'BalanceToBeInvoiced' in df_filtered.columns else 0.0
    received = float(df_filtered['TotalReceived'].sum()) if 'TotalReceived' in df_filtered.columns else 0.0

    return {
        "total_units": total_units,
        "sold": sold,
        "unsold": unsold,
        "sold_value": sold_value,
        "unsold_value": unsold_value,
        "invoiced": invoiced,
        "uninvoiced": uninvoiced,
        "received": received
    }

@app.get("/api/data")
def get_data(projects: Optional[List[str]] = Query(None)):
    df = fetch_data1()
    if projects and len(projects) > 0 and "All" not in projects:
        df_filtered = df[df["Project_Name"].isin(projects)]
    else:
        df_filtered = df
    df_clean = df_filtered.copy()
    df_clean = df_clean.where(pd.notnull(df_clean), None)
    return df_clean.to_dict(orient="records")

@app.get("/api/data2")
def get_data2():
    df = fetch_data2()
    df_clean = df.copy()
    df_clean = df_clean.where(pd.notnull(df_clean), None)
    return df_clean.to_dict(orient="records")

@app.get("/api/perspectives")
def get_perspectives():
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    p1 = get_profile1()
    p2 = get_profile2()
    
    profiles = {}
    if p1:
        profiles["Project Portfolio"] = p1
    if p2:
        profiles["Partner Collections"] = p2

    if gemini_key:
        try:
            col_summary = {k: v.get("numeric_cols", []) + v.get("categorical_cols", []) for k, v in profiles.items()}
            prompt = f"""
Given these real estate dataset columns:
{json.dumps(col_summary, indent=2)}

Suggest 6 concise executive focus areas for a board dashboard.
Return ONLY a JSON array of 6 strings. No markdown, no fences.
Each string should be an emoji + short business phrase (e.g. "📈 Revenue Performance by Project").
"""
            agent = Agent(model=Gemini(id="gemini-2.5-flash", api_key=gemini_key))
            res = agent.run(prompt)
            text = res.content if hasattr(res, "content") else str(res)
            clean = re.sub(r"```(?:json)?|```", "", text).strip()
            options = json.loads(clean)
            if isinstance(options, list) and len(options) >= 4:
                return options
        except Exception:
            pass

    # Fallbacks
    options = []
    if p1:
        for col in p1.get("top_numeric_by_variance", [])[:2]:
            options.append(f"📊 {col.replace('_',' ')} Analysis")
    if p2:
        for col in p2.get("top_numeric_by_variance", [])[:2]:
            options.append(f"💰 {col.replace('_',' ')} Analysis")
    if not options:
        options = ["📊 Portfolio Overview", "📈 Revenue Analysis", "💰 Collections Summary"]
    return options[:6]

@app.get("/api/charts")
def get_charts(perspective: str, projects: Optional[List[str]] = Query(None)):
    df1 = fetch_data1()
    p1 = get_profile1()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    if projects and len(projects) > 0 and "All" not in projects:
        df_filtered = df1[df1["Project_Name"].isin(projects)]
    else:
        df_filtered = df1

    if df_filtered.empty:
        return []

    profile_filtered = profile_dataframe(df_filtered)
    schema_summary = build_schema_summary(profile_filtered, df_filtered)

    specs = None
    if gemini_key:
        prompt = f"""
You are a data visualization expert for a C-suite real estate dashboard.
The user selected the focus area: "{perspective}"
The active dataset is: Project Portfolio

Here is the FULL schema and statistics for this dataset:
{schema_summary}

Based ONLY on the actual columns and data shown above, design 4 high-impact executive charts.

RULES:
- Every column name you reference MUST exist exactly in the schema above.
- Prefer columns with high variance for value axes.
- Use categorical columns with 2–30 unique values for grouping.
- Return ONLY a raw JSON array of exactly 4 objects. No markdown, no code fences.
Each object must have:
  "title": string
  "chart_type": "bar" | "pie" | "line" | "scatter"
  "x_col": string (exact column name)
  "y_col": string (exact column name)
  "names_col": string (exact column name — for pie charts)
  "values_col": string (exact column name — for pie charts)
  "orientation": "h" | "v"
  "colorscale": string (e.g. "emrld", "blues")
  "top_n": integer (5-15)
  "insight": string (one sentence grounded in actual data ranges)
"""
        try:
            agent = Agent(model=Gemini(id="gemini-2.5-flash", api_key=gemini_key))
            res = agent.run(prompt)
            text = res.content if hasattr(res, "content") else str(res)
            clean = re.sub(r"```(?:json)?|```", "", text).strip()
            specs = json.loads(clean)
        except Exception:
            specs = None

    # Fallback specs if LLM fails
    if not specs or not isinstance(specs, list) or len(specs) < 2:
        specs = []
        val_col = profile_filtered.get("best_value_col") or "TotalSalesRealization"
        cat_col = profile_filtered.get("best_category_col") or "Project_Name"
        
        if val_col in df_filtered.columns and cat_col in df_filtered.columns:
            specs.append({
                "title": f"Top Portfolios by {val_col.replace('_',' ')}",
                "chart_type": "bar",
                "x_col": val_col,
                "y_col": cat_col,
                "orientation": "h",
                "top_n": 8,
                "insight": "Overview of largest contributors."
            })
            specs.append({
                "title": f"Share of {val_col.replace('_',' ')} by Category",
                "chart_type": "pie",
                "names_col": cat_col,
                "values_col": val_col,
                "top_n": 6,
                "insight": "Proportional distribution of top assets."
            })

    # Prepare data for each chart spec to make it extremely easy for React to render
    response_charts = []
    for spec in specs[:4]:
        ctype = spec.get("chart_type", "bar")
        title = spec.get("title", "Metric Chart")
        insight = spec.get("insight", "")
        top_n = spec.get("top_n", 8)

        chart_data = []
        try:
            if ctype == "pie":
                names_col = spec.get("names_col") or spec.get("y_col") or "Project_Name"
                values_col = spec.get("values_col") or spec.get("x_col") or "TotalSalesRealization"
                if names_col in df_filtered.columns and values_col in df_filtered.columns:
                    plot_df = df_filtered[[names_col, values_col]].dropna()
                    plot_df = plot_df.groupby(names_col, as_index=False)[values_col].sum()
                    plot_df = plot_df.nlargest(top_n, values_col)
                    chart_data = [{"name": str(r[names_col]), "value": float(r[values_col])} for _, r in plot_df.iterrows()]
            else:
                x_col = spec.get("x_col")
                y_col = spec.get("y_col")
                if x_col in df_filtered.columns and y_col in df_filtered.columns:
                    plot_df = df_filtered[[x_col, y_col]].dropna()
                    # If x is numeric, sort, otherwise groupby
                    if pd.api.types.is_numeric_dtype(plot_df[x_col]) and not pd.api.types.is_numeric_dtype(plot_df[y_col]):
                        plot_df = plot_df.groupby(y_col, as_index=False)[x_col].sum()
                        plot_df = plot_df.nlargest(top_n, x_col)
                        chart_data = [{"name": str(r[y_col]), "value": float(r[x_col])} for _, r in plot_df.iterrows()]
                    elif pd.api.types.is_numeric_dtype(plot_df[y_col]) and not pd.api.types.is_numeric_dtype(plot_df[x_col]):
                        plot_df = plot_df.groupby(x_col, as_index=False)[y_col].sum()
                        plot_df = plot_df.nlargest(top_n, y_col)
                        chart_data = [{"name": str(r[x_col]), "value": float(r[y_col])} for _, r in plot_df.iterrows()]
                    else:
                        plot_df = plot_df.head(top_n)
                        chart_data = [{"name": str(r[x_col]), "value": float(r[y_col])} for _, r in plot_df.iterrows()]
            
            response_charts.append({
                "title": title,
                "chart_type": ctype,
                "insight": insight,
                "data": chart_data
            })
        except Exception:
            continue

    return response_charts

class ChatRequest(BaseModel):
    query: str
    projects: Optional[List[str]] = None

@app.post("/api/chat")
def run_chat_agent(body: ChatRequest):
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY missing from server configuration.")

    df1 = fetch_data1()
    df2 = fetch_data2()

    # Filter df1 by selected scope
    if body.projects and len(body.projects) > 0 and "All" not in body.projects:
        df1_filtered = df1[df1["Project_Name"].isin(body.projects)]
        scope_lbl = f"Projects: {', '.join(body.projects)}"
    else:
        df1_filtered = df1
        scope_lbl = "All Projects"

    profile1 = profile_dataframe(df1_filtered)
    profile2 = profile_dataframe(df2)

    profiles = {
        "api_data_1": profile1,
        "api_data_2": profile2
    }

    csv1_path = save_df_to_temp_csv(df1_filtered)
    csv2_path = save_df_to_temp_csv(df2)

    duckdb_tools = DuckDbTools()
    duckdb_tools.load_local_csv_to_table(path=csv1_path, table="api_data_1")
    duckdb_tools.load_local_csv_to_table(path=csv2_path, table="api_data_2")

    lines = [
        "You are a Chief Strategy Officer presenting to a real estate board.",
        f"Active scope: '{scope_lbl}'.",
        "You have access to the following datasets in DuckDB:",
    ]
    for table_name, profile in profiles.items():
        active_df = df1_filtered if table_name == "api_data_1" else df2
        schema_txt = build_schema_summary(profile, active_df)
        lines.append(f"\nTable '{table_name}':\n{schema_txt}")

    lines += [
        "\nSTRICT RULES:",
        "- Never use technical jargon (no SQL, DataFrame, API, JSON, statistical terms).",
        "- Express all financial values in ₹ Crores or ₹ Lakhs as appropriate.",
        "- Structure responses into exactly 3 sections:",
        "  1. 📌 Executive Overview (2-sentence direct answer)",
        "  2. 📊 Key Financial & Operational Findings (tables in ₹ Cr / ₹ L)",
        "  3. 💡 Strategic Board Recommendations (3 action items)",
    ]
    system_msg = "\n".join(lines)

    try:
        agent = Agent(
            model=Gemini(id="gemini-2.5-flash", api_key=gemini_key),
            tools=[duckdb_tools, PandasTools()],
            system_message=system_msg,
            markdown=True
        )
        response = agent.run(body.query)
        content = response.content if hasattr(response, "content") else str(response)
        
        try:
            os.remove(csv1_path)
            os.remove(csv2_path)
        except Exception:
            pass

        return {"answer": content}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Agent briefing failed: {str(e)}")

@app.post("/api/sync")
def sync_data():
    global _cached_df1, _cached_df2, _cached_profile1, _cached_profile2
    _cached_df1 = None
    _cached_df2 = None
    _cached_profile1 = None
    _cached_profile2 = None
    fetch_data1()
    fetch_data2()
    return {"status": "success", "message": "All database tables synchronized successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
