import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# --- 1. INITIAL SETTINGS ---
st.set_page_config(page_title="ISEM Hybrid Terminal", layout="wide", page_icon="⚡")

# Initialize variables to prevent "NameError"
df = None
mode = "Search"
actual_date = None

# Helper to parse SEM-O XML
def parse_sem_xml(content):
    try:
        root = ET.fromstring(content)
        rows = []
        for row in root.findall('.//Row'):
            rows.append({child.tag: child.text for child in row})
        return pd.DataFrame(rows)
    except Exception as e:
        return None

# --- 2. THE HYBRID DATA ENGINE ---
@st.cache_data(ttl=600)
def get_hybrid_data(target_date):
    base_url = "https://reports.sem-o.com/documents/"
    date_str = target_date.strftime('%Y%m%d')
    
    # STRATEGY A: Try Official 30-Min Settlement Reports
    # We try multiple publication stamps (1800, 1700, etc.)
    for t in ["1800", "1700", "2330", "1200"]:
        url = f"{base_url}PUB_30MinAvgImbalPrc_{date_str}{t}.xml"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = parse_sem_xml(r.content)
            if data is not None and not data.empty:
                return data, "Official Settlement", target_date

    # STRATEGY B: Fallback to 5-Min Indicative Reports (Scrape last 2 hours)
    indicative_data = []
    now = datetime.now()
    # Check every 5-min interval for the last 3 hours
    for m in range(0, 180, 5):
        check_time = (now - timedelta(minutes=m)).strftime('%H%M')
        url = f"{base_url}PUB_5MinImbalPrc_{date_str}{check_time}.xml"
        r = requests.get(url, timeout=2)
        if r.status_code == 200:
            temp_df = parse_sem_xml(r.content)
            if temp_df is not None: indicative_data.append(temp_df)
    
    if indicative_data:
        full_df = pd.concat(indicative_data).drop_duplicates()
        return full_df, "Indicative (Real-Time)", target_date
        
    return None, None, None

# --- 3. UI LAYOUT ---
st.title("🇮🇪 ISEM NIV & Price Terminal")
st.caption("Auto-switching between Official Settlement and Real-Time Indicative data.")

with st.sidebar:
    st.header("Terminal Settings")
    user_date = st.date_input("Analysis Date", datetime.now())
    st.info("On weekends or during maintenance, the app uses 5-min indicative data until the daily report is finalized.")

# Execute Data Fetch
df, mode, actual_date = get_hybrid_data(user_date)

# --- 4. DATA PROCESSING & FLEXIBLE COLUMN SNIFFING ---
if df is not None and not df.empty:
    # SNIFF: Find whichever price/volume columns SEM-O decided to use
    p_col = next((c for c in ['IMBALANCE_SETTLEMENT_PRICE', 'IMBALANCE_PRICE', 'NET_IMBALANCE_PRICE'] if c in df.columns), None)
    v_col = next((c for c in ['NET_IMBALANCE_VOLUME', 'QNIV', 'VOLUME'] if c in df.columns), None)
    t_col = 'START_TIME'

    if p_col and v_col:
        # Clean Data
        df[p_col] = pd.to_numeric(df[p_col], errors='coerce')
        df[v_col] = pd.to_numeric(df[v_col], errors='coerce')
        df[t_col] = pd.to_datetime(df[t_col])
        df = df.dropna(subset=[p_col, v_col]).sort_values(t_col)

        # AGGREGATE: If we have 5-min data, turn it into 30-min blocks
        if mode == "Indicative (Real-Time)":
            df = df.resample('30T', on=t_col).agg({v_col: 'sum', p_col: 'mean'}).reset_index()

        # --- 5. VISUALIZATION ---
        st.subheader(f"📊 {mode} Data: {actual_date.strftime('%d %B %Y')}")
        
        # Metric Cards
        c1, c2, c3 = st.columns(3)
        c1.metric("Avg Price", f"€{df[p_col].mean():.2f}")
        c2.metric("Max System Long", f"{df[v_col].max():.0f} MW")
        c3.metric("Max System Short", f"{df[v_col].min():.0f} MW")

        # Chart
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        colors = ['#EF553B' if x < 0 else '#636EFA' for x in df[v_col]]
        
        fig.add_trace(go.Bar(x=df[t_col], y=df[v_col], name="NIV (MW)", marker_color=colors), secondary_y=False)
        fig.add_trace(go.Scatter(x=df[t_col], y=df[p_col], name="Price (€)", line=dict(color='black', width=2)), secondary_y=True)
        
        fig.update_layout(hovermode="x unified", height=500, margin=dict(t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Raw Data Inspection"):
            st.write(df)
    else:
        st.error(f"Columns not found. Available: {df.columns.tolist()}")
else:
    st.error("No data found for this date. SEM-O may be offline for maintenance.")