import io
import os
import re
import tempfile
import csv
import json
import requests
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from dotenv import load_dotenv
from agno.agent import Agent
from agno.models.google import Gemini
from agno.tools.duckdb import DuckDbTools
from agno.tools.pandas import PandasTools

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Executive Multi-API Portfolio Portal",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

load_dotenv()

# ─── Styling ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { padding: 1.5rem 2.5rem; background-color: #0b1329; }
    .kpi-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155; border-radius: 12px;
        padding: 18px 22px; color: #f8fafc;
        box-shadow: 0 4px 14px rgba(0,0,0,0.25);
    }
    .kpi-card-alert {
        background: linear-gradient(135deg, #3f1d24 0%, #1f0b11 100%);
        border: 1px solid #831843; border-radius: 12px;
        padding: 18px 22px; color: #f8fafc;
        box-shadow: 0 4px 14px rgba(0,0,0,0.25);
    }
    .kpi-card-success {
        background: linear-gradient(135deg, #064e3b 0%, #022c22 100%);
        border: 1px solid #047857; border-radius: 12px;
        padding: 18px 22px; color: #f8fafc;
        box-shadow: 0 4px 14px rgba(0,0,0,0.25);
    }
    .kpi-title { font-size: 0.82rem; text-transform: uppercase; letter-spacing: 1.2px; color: #94a3b8; font-weight: 600; }
    .kpi-value { font-size: 1.7rem; font-weight: 700; margin-top: 4px; color: #38bdf8; }
    .kpi-value-alert { font-size: 1.7rem; font-weight: 700; margin-top: 4px; color: #f43f5e; }
    .kpi-value-success { font-size: 1.7rem; font-weight: 700; margin-top: 4px; color: #34d399; }
    .kpi-sub { font-size: 0.8rem; color: #64748b; margin-top: 2px; }
    .ai-insight-box {
        background-color: #1e293b; border-left: 4px solid #38bdf8;
        padding: 12px 16px; border-radius: 6px;
        margin-top: 8px; margin-bottom: 24px;
        font-size: 0.88rem; color: #cbd5e1;
    }
    .schema-badge {
        background-color: #1e293b; border: 1px solid #334155;
        padding: 4px 10px; border-radius: 20px;
        font-size: 0.75rem; color: #94a3b8; display: inline-block; margin: 2px;
    }
    .stButton>button { border-radius: 8px; font-weight: 600; }
    h1, h2, h3 { color: #f8fafc; font-family: 'Inter', sans-serif; }
</style>
""", unsafe_allow_html=True)


# ─── Schema Profiler ──────────────────────────────────────────────────────────

def profile_dataframe(df: pd.DataFrame) -> dict:
    """
    Fully inspect a DataFrame and return a rich schema profile used by all
    downstream components — chart generation, KPI cards, AI prompts.
    """
    profile = {
        "row_count": len(df),
        "col_count": len(df.columns),
        "numeric_cols": [],
        "categorical_cols": [],
        "date_cols": [],
        "id_like_cols": [],       # high-cardinality strings (names, IDs)
        "low_card_cols": [],      # low-cardinality strings (good for groupby)
        "col_stats": {},
        "top_numeric_by_variance": [],  # best cols for bar/scatter value axis
        "best_category_col": None,      # best col for groupby / pie names
        "best_value_col": None,         # best numeric col for aggregation
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
                "std": float(series.std()) if len(series) > 1 else 0.0,
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

    # Rank numeric cols by variance (most informative for charts)
    if profile["numeric_cols"]:
        ranked = sorted(
            profile["numeric_cols"],
            key=lambda c: profile["col_stats"][c].get("std", 0),
            reverse=True
        )
        profile["top_numeric_by_variance"] = ranked

        # Best "value" col: prefer cols whose name hints at money/amount/revenue
        money_hints = ["revenue", "amount", "total", "receipt", "sales", "value",
                       "realized", "invoiced", "received", "cr", "lakh"]
        for col in ranked:
            if any(h in col.lower() for h in money_hints):
                profile["best_value_col"] = col
                break
        if not profile["best_value_col"] and ranked:
            profile["best_value_col"] = ranked[0]

    # Best category col: prefer cols whose name hints at names/projects/partners
    name_hints = ["name", "project", "partner", "registration", "location",
                  "type", "category", "area", "zone", "city"]
    cat_candidates = profile["low_card_cols"] + profile["id_like_cols"]
    for col in cat_candidates:
        if any(h in col.lower() for h in name_hints):
            profile["best_category_col"] = col
            break
    if not profile["best_category_col"] and cat_candidates:
        profile["best_category_col"] = cat_candidates[0]

    return profile


def build_schema_summary(profile: dict, df: pd.DataFrame) -> str:
    """Build a concise schema summary string for LLM prompts."""
    lines = [
        f"Rows: {profile['row_count']} | Columns: {profile['col_count']}",
        f"Numeric columns: {profile['numeric_cols']}",
        f"Categorical columns: {profile['categorical_cols']}",
        f"Date columns: {profile['date_cols']}",
        "Column statistics:"
    ]
    for col, stats in profile["col_stats"].items():
        lines.append(f"  {col}: {stats}")

    lines.append(f"\nSample records (first 5):")
    lines.append(df.head(5).to_string(index=False))
    return "\n".join(lines)


# ─── Data Ingestion ───────────────────────────────────────────────────────────

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
    """Automatically infer and coerce column types after loading."""
    for col in df.columns:
        if "date" in col.lower() or "time" in col.lower():
            df[col] = pd.to_datetime(df[col], errors="coerce")
        elif df[col].dtype == "object":
            converted = pd.to_numeric(df[col], errors="coerce")
            # Only convert if <10% become NaN (i.e., mostly numeric)
            if converted.notna().sum() / max(len(df), 1) > 0.9:
                df[col] = converted
    return df


def fetch_api_dataset(url_key, method_key, hkey_key, hval_key, payload_key) -> pd.DataFrame | None:
    url = os.getenv(url_key, "").strip()
    if not url:
        return None

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


def save_df_to_temp_csv(df: pd.DataFrame) -> str:
    df_clean = df.copy()
    for col in df_clean.select_dtypes(include=["object"]):
        df_clean[col] = df_clean[col].astype(str).replace({r'"': '""'}, regex=True)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as f:
        df_clean.to_csv(f.name, index=False, quoting=csv.QUOTE_ALL)
        return f.name


# ─── Dynamic KPI Builder ──────────────────────────────────────────────────────

def format_kpi_value(val, prefix=""):
    if val > 1e7:
        return f"{prefix}{val/1e7:,.2f} Cr"
    elif val > 1e5:
        return f"{prefix}{val/1e5:,.2f} L"
    elif val > 1e3:
        return f"{prefix}{val/1e3:,.2f}K"
    else:
        return f"{prefix}{val:,.2f}"

def render_project_kpis(df_filtered: pd.DataFrame):
    """
    Render exact KPIs requested: Total units, sold, unsold, sold value, unsold value, invoice amt, uninvoiced.
    """
    total_units = int(df_filtered['TotalInventory'].sum()) if 'TotalInventory' in df_filtered.columns else 0
    sold = int(df_filtered['SoldInventory'].sum()) if 'SoldInventory' in df_filtered.columns else 0
    unsold = int(df_filtered['AvailableInventory'].sum()) if 'AvailableInventory' in df_filtered.columns else 0
    sold_value = df_filtered['TotalSalesRealization'].sum() if 'TotalSalesRealization' in df_filtered.columns else 0.0
    
    # Calculate unsold value row-by-row
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
    unsold_value = sum(unsold_values)
    
    invoice_amt = df_filtered['TotalInvoiced'].sum() if 'TotalInvoiced' in df_filtered.columns else 0.0
    uninvoiced = df_filtered['BalanceToBeInvoiced'].sum() if 'BalanceToBeInvoiced' in df_filtered.columns else 0.0

    st.markdown("#### 📌 Key Metrics")
    cols = st.columns(7)
    kpis = [
        ("Total Units", f"{total_units:,}", "kpi-card"),
        ("Sold", f"{sold:,}", "kpi-card-success"),
        ("Unsold", f"{unsold:,}", "kpi-card-alert"),
        ("Sold Value", format_kpi_value(sold_value, "₹"), "kpi-card-success"),
        ("Unsold Value", format_kpi_value(unsold_value, "₹"), "kpi-card-alert"),
        ("Invoice Amt", format_kpi_value(invoice_amt, "₹"), "kpi-card"),
        ("Uninvoiced", format_kpi_value(uninvoiced, "₹"), "kpi-card-alert")
    ]
    
    for col, (title, value, css_class) in zip(cols, kpis):
        val_class = "kpi-value"
        if "success" in css_class:
            val_class = "kpi-value-success"
        elif "alert" in css_class:
            val_class = "kpi-value-alert"
            
        with col:
            st.markdown(f"""
            <div class="{css_class}">
                <div class="kpi-title">{title}</div>
                <div class="{val_class}">{value}</div>
            </div>""", unsafe_allow_html=True)


# ─── Dynamic Chart Generation via LLM ────────────────────────────────────────

CHART_FALLBACK_COLORS = ["emrld", "purples", "tealgrn", "blues", "reds", "viridis"]


def generate_llm_chart_specs(
    df: pd.DataFrame,
    profile: dict,
    perspective: str,
    api_label: str,
    gemini_key: str
) -> list | None:
    """
    Ask Gemini to generate chart specs grounded in the ACTUAL schema and stats.
    Returns a list of chart spec dicts or None on failure.
    """
    if not gemini_key or df is None:
        return None

    schema_summary = build_schema_summary(profile, df)

    prompt = f"""
You are a data visualization expert for a C-suite real estate dashboard.
The user selected the focus area: "{perspective}"
The active dataset is: {api_label}

Here is the FULL schema and statistics for this dataset:
{schema_summary}

Based ONLY on the actual columns and data shown above, design 4 high-impact executive charts.

RULES:
- Every column name you reference MUST exist exactly in the schema above.
- Prefer columns with high variance for value axes.
- Use categorical columns with 2–30 unique values for grouping/pie slices.
- For bar charts with many categories, recommend top_n = 8-12.
- Provide a specific, data-grounded insight for each chart.

Return ONLY a raw JSON array of exactly 4 objects. No markdown, no code fences.
Each object must have:
  "title": string
  "chart_type": "bar" | "pie" | "line" | "scatter"
  "x_col": string (exact column name — for bar/scatter/line)
  "y_col": string (exact column name — for bar/scatter/line)
  "names_col": string (exact column name — for pie)
  "values_col": string (exact column name — for pie)
  "orientation": "h" | "v"
  "colorscale": one of ["emrld", "reds", "tealgrn", "blues", "purples", "viridis"]
  "top_n": integer (5-15)
  "insight": string (one sentence grounded in actual data ranges from the stats above)
"""

    try:
        agent = Agent(model=Gemini(id="gemini-2.5-flash", api_key=gemini_key))
        res = agent.run(prompt)
        text = res.content if hasattr(res, "content") else str(res)
        # Strip any accidental markdown fences
        clean = re.sub(r"```(?:json)?|```", "", text).strip()
        specs = json.loads(clean)
        if isinstance(specs, list) and len(specs) >= 2:
            # Validate all referenced columns exist
            valid_specs = []
            for s in specs:
                ctype = s.get("chart_type", "bar")
                if ctype == "pie":
                    if s.get("names_col") in df.columns and s.get("values_col") in df.columns:
                        valid_specs.append(s)
                else:
                    if s.get("x_col") in df.columns and s.get("y_col") in df.columns:
                        valid_specs.append(s)
            if len(valid_specs) >= 2:
                return valid_specs
    except Exception as e:
        st.warning(f"LLM chart generation issue: {e}. Using schema-driven fallback charts.")

    return None


def build_fallback_charts(df: pd.DataFrame, profile: dict) -> list:
    """
    Build 4 sensible fallback chart specs purely from the schema profile.
    Zero hardcoded column names.
    """
    specs = []
    value_col = profile.get("best_value_col")
    cat_col = profile.get("best_category_col")
    numeric_cols = profile.get("top_numeric_by_variance", [])
    color_cycle = CHART_FALLBACK_COLORS

    # Chart 1: Top categories by best value col (horizontal bar)
    if cat_col and value_col:
        specs.append({
            "title": f"Top {cat_col.replace('_',' ')} by {value_col.replace('_',' ')}",
            "chart_type": "bar",
            "x_col": value_col, "y_col": cat_col,
            "orientation": "h", "colorscale": color_cycle[0],
            "top_n": 10,
            "insight": f"Ranks all {cat_col.replace('_',' ')} entries by their total {value_col.replace('_',' ')} contribution."
        })

    # Chart 2: Second numeric col bar or pie
    if cat_col and len(numeric_cols) >= 2:
        second_val = numeric_cols[1]
        specs.append({
            "title": f"{second_val.replace('_',' ')} by {cat_col.replace('_',' ')}",
            "chart_type": "bar",
            "x_col": second_val, "y_col": cat_col,
            "orientation": "h", "colorscale": color_cycle[1],
            "top_n": 10,
            "insight": f"Compares {second_val.replace('_',' ')} across all {cat_col.replace('_',' ')} groups."
        })

    # Chart 3: Pie distribution of value col by category
    if cat_col and value_col:
        specs.append({
            "title": f"{value_col.replace('_',' ')} Share by {cat_col.replace('_',' ')}",
            "chart_type": "pie",
            "names_col": cat_col, "values_col": value_col,
            "orientation": "v", "colorscale": color_cycle[2],
            "top_n": 10,
            "insight": f"Shows proportional share of {value_col.replace('_',' ')} across all groups."
        })

    # Chart 4: If a low-cardinality second category exists, use it; else use 3rd numeric
    second_cat = next(
        (c for c in profile["low_card_cols"] if c != cat_col),
        None
    )
    if second_cat and value_col:
        specs.append({
            "title": f"{value_col.replace('_',' ')} by {second_cat.replace('_',' ')}",
            "chart_type": "bar",
            "x_col": second_cat, "y_col": value_col,
            "orientation": "v", "colorscale": color_cycle[3],
            "top_n": 12,
            "insight": f"Breaks down {value_col.replace('_',' ')} by {second_cat.replace('_',' ')} category."
        })
    elif len(numeric_cols) >= 3 and cat_col:
        third_val = numeric_cols[2]
        specs.append({
            "title": f"{third_val.replace('_',' ')} Distribution",
            "chart_type": "bar",
            "x_col": third_val, "y_col": cat_col,
            "orientation": "h", "colorscale": color_cycle[3],
            "top_n": 10,
            "insight": f"Ranks {cat_col.replace('_',' ')} by {third_val.replace('_',' ')}."
        })

    # Ensure we always have 4
    while len(specs) < 4 and len(numeric_cols) >= 2:
        idx = len(specs)
        specs.append({
            "title": f"{numeric_cols[idx % len(numeric_cols)].replace('_',' ')} Overview",
            "chart_type": "bar",
            "x_col": numeric_cols[0], "y_col": numeric_cols[min(1, len(numeric_cols)-1)],
            "orientation": "h", "colorscale": color_cycle[idx % len(color_cycle)],
            "top_n": 10,
            "insight": "Key numeric metric overview."
        })

    return specs[:4]


def render_chart_spec(spec: dict, df: pd.DataFrame):
    """Render a single chart spec against a live DataFrame."""
    try:
        ctype = str(spec.get("chart_type", "bar")).lower()
        title = spec.get("title", "Chart")
        insight = spec.get("insight", "")
        colorscale = spec.get("colorscale", "emrld")
        if colorscale not in CHART_FALLBACK_COLORS:
            colorscale = "purples"

        if "pie" in ctype or "donut" in ctype:
            names_col = spec.get("names_col")
            values_col = spec.get("values_col")
            if names_col not in df.columns or values_col not in df.columns:
                st.warning(f"Column mismatch for chart '{title}'")
                return
            plot_df = df[[names_col, values_col]].dropna()
            plot_df = plot_df.groupby(names_col, as_index=False)[values_col].sum()
            plot_df = plot_df.nlargest(spec.get("top_n", 10), values_col)
            fig = px.pie(
                plot_df, names=names_col, values=values_col,
                title=f"📊 {title}", hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Bold
            )

        elif ctype == "scatter":
            x_col = spec.get("x_col")
            y_col = spec.get("y_col")
            if x_col not in df.columns or y_col not in df.columns:
                st.warning(f"Column mismatch for chart '{title}'")
                return
            fig = px.scatter(
                df, x=x_col, y=y_col,
                title=f"📊 {title}",
                color_discrete_sequence=["#38bdf8"]
            )

        elif ctype == "line":
            x_col = spec.get("x_col")
            y_col = spec.get("y_col")
            if x_col not in df.columns or y_col not in df.columns:
                st.warning(f"Column mismatch for chart '{title}'")
                return
            plot_df = df[[x_col, y_col]].dropna().sort_values(x_col)
            fig = px.line(
                plot_df, x=x_col, y=y_col,
                title=f"📊 {title}",
                color_discrete_sequence=["#38bdf8"]
            )

        else:  # bar
            x_col = spec.get("x_col")
            y_col = spec.get("y_col")
            orient = spec.get("orientation", "h")
            if x_col not in df.columns or y_col not in df.columns:
                st.warning(f"Column mismatch for chart '{title}'")
                return

            sort_col = x_col if orient == "h" else y_col
            if pd.api.types.is_numeric_dtype(df[sort_col]):
                plot_df = df.nlargest(spec.get("top_n", 10), sort_col)
            else:
                plot_df = df.head(spec.get("top_n", 10))

            color_col = x_col if orient == "h" else y_col
            fig = px.bar(
                plot_df, x=x_col, y=y_col,
                orientation=orient,
                title=f"📊 {title}",
                color=color_col if pd.api.types.is_numeric_dtype(df[color_col]) else None,
                color_continuous_scale=colorscale
            )

        fig.update_layout(
            height=420,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(15,23,42,0.8)",
            font_color="#cbd5e1",
            title_font_color="#f8fafc",
        )
        st.plotly_chart(fig, use_container_width=True)
        if insight:
            st.markdown(
                f'<div class="ai-insight-box">💡 <b>Executive Insight:</b> {insight}</div>',
                unsafe_allow_html=True
            )

    except Exception as e:
        st.error(f"Chart render error — '{spec.get('title', '')}': {e}")


# ─── Dynamic Focus Perspectives via LLM ──────────────────────────────────────

def get_dynamic_perspectives(profiles: dict, gemini_key: str) -> list[str]:
    """
    Ask Gemini to suggest focus areas based on actual column names.
    Falls back to schema-derived defaults if LLM unavailable.
    """
    if gemini_key:
        try:
            col_summary = {k: v["numeric_cols"] + v["categorical_cols"]
                           for k, v in profiles.items()}
            prompt = f"""
Given these real estate dataset columns:
{json.dumps(col_summary, indent=2)}

Suggest 6 concise executive focus areas for a board dashboard.
Return ONLY a JSON array of 6 strings. No markdown.
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

    # Schema-derived fallback
    options = []
    for label, profile in profiles.items():
        for col in profile.get("top_numeric_by_variance", [])[:2]:
            options.append(f"📊 {col.replace('_',' ')} Analysis — {label}")
    if not options:
        options = ["📊 Portfolio Overview", "📈 Revenue Analysis", "💰 Collections Summary"]
    return options[:7]


# ─── Dynamic AI Agent System Message ─────────────────────────────────────────

def build_agent_system_message(profiles: dict, dataset_toggle: str) -> str:
    """Build an AI system message entirely from the actual schema profiles."""
    lines = [
        "You are a Chief Strategy Officer presenting to a real estate board.",
        f"Active scope: '{dataset_toggle}'.",
        "You have access to the following datasets in DuckDB:",
    ]
    for table_name, profile in profiles.items():
        schema_txt = build_schema_summary(profile, st.session_state.get(table_name.replace("api_data_", "df"), pd.DataFrame()))
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
    return "\n".join(lines)


# ─── Data Loading ─────────────────────────────────────────────────────────────

if "df1" not in st.session_state:
    with st.spinner("Connecting to Real Estate Portfolio System..."):
        try:
            st.session_state.df1 = fetch_api_dataset(
                "API_1_URL", "API_1_METHOD", "API_1_HEADER_KEY", "API_1_HEADER_VALUE", "API_1_PAYLOAD"
            )
        except Exception as e:
            st.session_state.df1 = None

if "df2" not in st.session_state:
    with st.spinner("Connecting to Channel Partner Collections System..."):
        try:
            st.session_state.df2 = fetch_api_dataset(
                "API_2_URL", "API_2_METHOD", "API_2_HEADER_KEY", "API_2_HEADER_VALUE", "API_2_PAYLOAD"
            )
        except Exception as e:
            st.session_state.df2 = None

df1: pd.DataFrame | None = st.session_state.get("df1")
df2: pd.DataFrame | None = st.session_state.get("df2")
gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

# Profile both DataFrames — source of truth for all downstream logic
if "profile1" not in st.session_state:
    st.session_state.profile1 = profile_dataframe(df1) if df1 is not None else {}
if "profile2" not in st.session_state:
    st.session_state.profile2 = profile_dataframe(df2) if df2 is not None else {}

profile1: dict = st.session_state.get("profile1", {})
profile2: dict = st.session_state.get("profile2", {})

# Build combined profile index for multi-dataset views
active_profiles = {}
if df1 is not None:
    active_profiles["api_data_1"] = profile1
if df2 is not None:
    active_profiles["api_data_2"] = profile2


# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🏢 Executive Project Portal")

    if df1 is not None:
        project_list = ["All Projects"] + sorted(df1["Project_Name"].dropna().unique().tolist())
        selected_project = st.selectbox(
            "Select Project to Analyze:",
            options=project_list,
            index=0
        )
    else:
        st.warning("No project data loaded.")
        selected_project = "All Projects"

    st.markdown("---")
    if st.button("🔄 Sync Live API Data"):
        for key in ["df1", "df2", "profile1", "profile2", "llm_charts_cache", "perspectives_cache"]:
            st.session_state.pop(key, None)
        st.rerun()


# ─── Header ───────────────────────────────────────────────────────────────────

st.title("🏢 Executive Board Dashboard Portal")
st.markdown(f"Schema-Adaptive Business Intelligence • Selected Project: **{selected_project}**")

if df1 is None and df2 is None:
    st.warning("⚠️ No API data loaded. Check your `.env` credentials.")
    st.stop()


# ─── DuckDB Setup ─────────────────────────────────────────────────────────────

duckdb_tools = DuckDbTools()
if df1 is not None:
    duckdb_tools.load_local_csv_to_table(path=save_df_to_temp_csv(df1), table="api_data_1")
if df2 is not None:
    duckdb_tools.load_local_csv_to_table(path=save_df_to_temp_csv(df2), table="api_data_2")


# ─── Tabs ─────────────────────────────────────────────────────────────────────

dashboard_tab, query_tab, data_tab = st.tabs([
    "📊 Schema-Driven Dashboards",
    "💬 AI Executive Strategy Assistant",
    "📄 Live API Data Statements"
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Schema-Driven Dashboards
# ═══════════════════════════════════════════════════════════════════════════════

with dashboard_tab:

    # Determine active DF and profile based on selected project
    if df1 is not None:
        if selected_project != "All Projects":
            active_df = df1[df1["Project_Name"] == selected_project]
        else:
            active_df = df1
        active_profile = profile_dataframe(active_df)
        active_label = f"Project Portfolio: {selected_project}"
    else:
        active_df = None
        active_profile = {}
        active_label = "No Data"

    if active_df is None or len(active_df) == 0:
        st.info("No data available for the selected scope.")
    else:
        # ── KPI Cards ──────────────────────────────────────────────────────────
        render_project_kpis(active_df)

        st.markdown("---")

        # ── Focus Perspective Selector ─────────────────────────────────────────
        if "perspectives_cache" not in st.session_state:
            with st.spinner("Generating executive focus areas from your data..."):
                st.session_state.perspectives_cache = get_dynamic_perspectives(
                    active_profiles, gemini_key
                )

        perspectives = st.session_state.perspectives_cache
        selected_perspective = st.selectbox(
            "Select Executive Focus Area (auto-generated from your data schema):",
            options=perspectives
        )

        st.markdown("---")

        # ── Chart Generation ───────────────────────────────────────────────────
        cache_key = f"{selected_project}_{selected_perspective}"
        if "llm_charts_cache" not in st.session_state:
            st.session_state.llm_charts_cache = {}

        header_a, header_b = st.columns([3, 1])
        with header_a:
            st.subheader(f"🤖 AI-Generated Charts: {selected_perspective}")
            st.caption("Charts are built from your actual data schema — column names, stats, and distributions.")
        with header_b:
            if st.button("🔄 Regenerate Charts"):
                st.session_state.llm_charts_cache.pop(cache_key, None)
                st.rerun()

        # Get or generate specs
        specs = st.session_state.llm_charts_cache.get(cache_key)
        if specs is None:
            with st.spinner("Analyzing schema and generating tailored charts..."):
                specs = generate_llm_chart_specs(
                    active_df, active_profile, selected_perspective,
                    active_label, gemini_key
                )
                if specs is None:
                    specs = build_fallback_charts(active_df, active_profile)
                st.session_state.llm_charts_cache[cache_key] = specs

        # Render in 2-column grid
        for i in range(0, len(specs), 2):
            col_a, col_b = st.columns(2)
            for col_ui, idx in [(col_a, i), (col_b, i + 1)]:
                if idx < len(specs):
                    with col_ui:
                        render_chart_spec(specs[idx], active_df)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — AI Executive Strategy Assistant
# ═══════════════════════════════════════════════════════════════════════════════

with query_tab:
    st.subheader("💬 AI Executive Strategy Assistant")
    st.caption(f"Model: **gemini-2.5-flash** • Selected Project: **{selected_project}** • Schema-aware system prompt")

    # Dynamic preset buttons from schema
    st.markdown("**Quick Analysis Prompts (auto-generated from your data):**")
    preset_cols = st.columns(4)
    preset_query = ""

    def make_preset(profile: dict, label: str) -> str:
        val = profile.get("best_value_col", "")
        cat = profile.get("best_category_col", "")
        if val and cat:
            return f"Show me the top 10 {cat.replace('_',' ')} entries ranked by {val.replace('_',' ')}. Format values in ₹ Crores."
        return f"Summarise the key financial metrics in {label}."

    presets = []
    if df1 is not None:
        presets.append(("🏆 Top Performers (Portfolio)", make_preset(profile1, "Portfolio")))
        presets.append(("⚠️ Risk Exposure (Portfolio)",
            f"Which {profile1.get('best_category_col','records').replace('_',' ')} have the highest financial risk? Identify gaps."))
    if df2 is not None:
        presets.append(("💳 Top Partners (Collections)", make_preset(profile2, "Collections")))
        presets.append(("📋 Collections Brief (Collections)",
            f"Provide an executive briefing on channel partner collection performance."))

    if not presets:
        presets = [("📊 Overview", "Provide a full executive summary of all available data.")]

    for i, (label, q) in enumerate(presets[:4]):
        with preset_cols[i % 4]:
            if st.button(label):
                preset_query = q

    user_query = st.text_area(
        "Ask a strategic question:",
        value=preset_query or st.session_state.get("last_query", ""),
        placeholder="e.g. Which projects have the highest outstanding receivables?",
        height=100
    )

    if st.button("📊 Generate Executive Briefing", type="primary"):
        if not gemini_key:
            st.error("GEMINI_API_KEY missing from `.env`.")
        elif not user_query.strip():
            st.warning("Please enter a business question.")
        else:
            st.session_state.last_query = user_query
            try:
                system_msg = build_agent_system_message(active_profiles, selected_project)
                agent = Agent(
                    model=Gemini(id="gemini-2.5-flash", api_key=gemini_key),
                    tools=[duckdb_tools, PandasTools()],
                    system_message=system_msg,
                    markdown=True
                )
                with st.spinner("Generating executive briefing..."):
                    response = agent.run(user_query)
                    content = response.content if hasattr(response, "content") else str(response)
                st.markdown("---")
                st.markdown(content)
            except Exception as e:
                st.error(f"Unable to generate executive brief: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Live Data Statements
# ═══════════════════════════════════════════════════════════════════════════════

with data_tab:
    st.subheader("📄 Live API Data Statements")
    t1, t2 = st.tabs(["API 1: Project Portfolio", "API 2: Partner Collections"])

    with t1:
        if df1 is not None:
            st.write(f"**{profile1['row_count']}** rows × **{profile1['col_count']}** columns")
            col_filter = st.multiselect(
                "Filter columns to display:",
                options=df1.columns.tolist(),
                default=df1.columns.tolist()[:10],
                key="df1_cols"
            )
            st.dataframe(df1[col_filter] if col_filter else df1, use_container_width=True)
            st.download_button(
                "⬇️ Download API 1 as CSV",
                data=df1.to_csv(index=False),
                file_name="portfolio_data.csv",
                mime="text/csv"
            )
        else:
            st.info("API 1 data not loaded.")

    with t2:
        if df2 is not None:
            st.write(f"**{profile2['row_count']}** rows × **{profile2['col_count']}** columns")
            col_filter2 = st.multiselect(
                "Filter columns to display:",
                options=df2.columns.tolist(),
                default=df2.columns.tolist()[:10],
                key="df2_cols"
            )
            st.dataframe(df2[col_filter2] if col_filter2 else df2, use_container_width=True)
            st.download_button(
                "⬇️ Download API 2 as CSV",
                data=df2.to_csv(index=False),
                file_name="collections_data.csv",
                mime="text/csv"
            )
        else:
            st.info("API 2 data not loaded.")