import os
import json
import requests
import pandas as pd
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load env variables from root directory
load_dotenv(dotenv_path="../.env")
if not os.getenv("API_1_URL"):
    load_dotenv(dotenv_path=".env")

app = FastAPI(title="Project Analytics API")

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global cache for the dataframe
_cached_df: Optional[pd.DataFrame] = None

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

def fetch_data() -> pd.DataFrame:
    global _cached_df
    if _cached_df is not None:
        return _cached_df

    url = os.getenv("API_1_URL", "").strip()
    if not url:
        raise HTTPException(status_code=500, detail="API_1_URL not configured in environment")

    method = os.getenv("API_1_METHOD", "POST").strip().upper()
    hkey = os.getenv("API_1_HEADER_KEY", "").strip()
    hval = os.getenv("API_1_HEADER_VALUE", "").strip()
    payload_raw = os.getenv("API_1_PAYLOAD", "").strip()

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

    try:
        response = requests.request(method=method, url=url, **kwargs)
        response.raise_for_status()
        try:
            df = json_to_df(response.json())
        except Exception:
            import io
            df = pd.read_csv(io.StringIO(response.text))
        
        df = coerce_column_types(df)
        _cached_df = df
        return df
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch data from upstream API: {str(e)}")

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
    df = fetch_data()
    if "Project_Name" not in df.columns:
        return []
    projects = df["Project_Name"].dropna().unique().tolist()
    return sorted([str(p) for p in projects])

@app.get("/api/kpis", response_model=KPIResponse)
def get_kpis(projects: Optional[List[str]] = Query(None)):
    df = fetch_data()
    
    # Filter by projects if supplied
    if projects and len(projects) > 0 and "All" not in projects:
        df_filtered = df[df["Project_Name"].isin(projects)]
    else:
        df_filtered = df

    total_units = int(df_filtered['TotalInventory'].sum()) if 'TotalInventory' in df_filtered.columns else 0
    sold = int(df_filtered['SoldInventory'].sum()) if 'SoldInventory' in df_filtered.columns else 0
    unsold = int(df_filtered['AvailableInventory'].sum()) if 'AvailableInventory' in df_filtered.columns else 0
    sold_value = float(df_filtered['TotalSalesRealization'].sum()) if 'TotalSalesRealization' in df_filtered.columns else 0.0
    
    # Unsold value calculation
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
    df = fetch_data()
    if projects and len(projects) > 0 and "All" not in projects:
        df_filtered = df[df["Project_Name"].isin(projects)]
    else:
        df_filtered = df
    
    # Replace NaN with None for valid JSON serialization
    df_clean = df_filtered.copy()
    df_clean = df_clean.where(pd.notnull(df_clean), None)
    return df_clean.to_dict(orient="records")

@app.post("/api/sync")
def sync_data():
    global _cached_df
    _cached_df = None
    fetch_data()
    return {"status": "success", "message": "Data cache updated successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
