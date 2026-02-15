import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# --- CONFIG ---
st.set_page_config(page_title="ISEM Hybrid Terminal", layout="wide")

def parse_sem_xml(content):
    root = ET.fromstring(content)
    rows = []
    for row in root.findall('.//Row'):
        rows.append({child.tag: child.text for child in row})
    return pd.DataFrame(rows)

@st.cache_data(ttl=600) # Faster refresh for real-time data
def get_hybrid_data(target_date):
    base_url = "https://reports.sem-o.com/documents/"
    date_str = target_date.strftime('%Y%m%d')
    
    # --- STRATEGY 1: Try Official 30-Min Report first ---
    # Common settlement publication times
    for t in ["1800", "1700", "2330", "1200"]:
        url = f"{base_url}PUB_30MinAvgImbalPrc_{date_str}{t}.xml"
        r = requests.get(url)
        if r.status_code == 200:
            df = parse_sem_xml(r.content)
            df['SOURCE'] = "OFFICIAL SETTLEMENT"
            return df, "Official"

    # --- STRATEGY 2: Try 5-Min Indicative Reports (The "Real-Time" Mode) ---
    # We grab the most recent hour of 5-min data if the daily report is missing
    st.sidebar.info("Official report not found. Switching to Indicative 5-Min mode...")
    indicative_data = []
    
    # Scan the last 3 hours in 5-min chunks
    now = datetime.now()
    for m in range(0, 180, 5):
        check_time = (now - timedelta(minutes=m)).strftime('%H%M')
        # Standard indicative filename: PUB_5MinImbalPrc_YYYYMMDDHHMM.xml
        url = f"{base_url}PUB_5MinImbalPrc_{date_str}{check_time}.xml"
        r = requests.get(url)
        if r.status_code == 200:
            temp_df = parse_sem_xml(r.content)
            indicative_data.append(temp_df)
    
    if indicative_data:
        full_df = pd.concat(indicative_data).drop_duplicates()
        full_df['SOURCE'] = "INDICATIVE (5-MIN)"
        return full_df, "Indicative"
        
    return None, None

# --- UI LOGIC ---
st.title("🇮🇪 ISEM Hybrid Market Terminal")
target_date = st.sidebar.date_input("Analysis Date", datetime.now())

df, mode = get_hybrid_data(target_date)

if df is not None:
    # Standardize columns for both report types
    # 5-min reports often use 'IMBALANCE_PRICE' instead of 'IMBALANCE_SETTLEMENT_PRICE'
    price_col = 'IMBALANCE_SETTLEMENT_PRICE' if 'IMBALANCE_SETTLEMENT_PRICE' in df.columns else 'IMBALANCE_PRICE'
    df[price_col] = pd.to_numeric(df[price_col])
    df['NET_IMBALANCE_VOLUME'] = pd.to_numeric(df['NET_IMBALANCE_VOLUME'])
    df['START_TIME'] = pd.to_datetime(df['START_TIME'])
    df = df.sort_values('START_TIME')

    # If in Indicative mode, aggregate to 30-min for a cleaner chart
    if mode == "Indicative":
        df = df.resample('30T', on='START_TIME').agg({
            'NET_IMBALANCE_VOLUME': 'sum', 
            price_col: 'mean'
        }).reset_index()

    # --- PLOTTING ---
    st.subheader(f"Mode: {mode} Data ({target_date.strftime('%d %b')})")
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    colors = ['#EF553B' if x < 0 else '#636EFA' for x in df['NET_IMBALANCE_VOLUME']]
    
    fig.add_trace(go.Bar(x=df['START_TIME'], y=df['NET_IMBALANCE_VOLUME'], name="NIV (MW)", marker_color=colors), secondary_y=False)
    fig.add_trace(go.Scatter(x=df['START_TIME'], y=df[price_col], name="Price (€)", line=dict(color='black')), secondary_y=True)
    
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df)
else:
    st.error("No reports found. SEM-O server may be in maintenance.")