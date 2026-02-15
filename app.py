import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# --- CONFIG ---
st.set_page_config(page_title="ISEM NIV Tracker", layout="wide")

@st.cache_data(ttl=3600) # Auto-refresh data every hour if the page is open
def get_isem_data(date_obj):
    report_list_url = "https://reports.sem-o.com/api/v1/dynamic/reports"
    doc_url_base = "https://reports.sem-o.com/documents/"
    
    # 1. Query Report List
    params = {
        'ReportName': 'Imbalance Price Report (Imbalance Settlement Period)',
        'Date': date_obj.strftime('%Y-%m-%d'),
        'page_size': 5
    }
    
    try:
        r = requests.get(report_list_url, params=params, timeout=10)
        items = r.json().get('items', [])
        if not items: return None
        
        # 2. Get latest ResourceName
        resource = items[0]['ResourceName']
        data_r = requests.get(f"{doc_url_base}{resource}", timeout=10)
        
        # 3. Parse XML to Dataframe
        root = ET.fromstring(data_r.content)
        rows = [{child.tag: child.text for child in row} for row in root.findall('.//Row')]
        
        df = pd.DataFrame(rows)
        df['NET_IMBALANCE_VOLUME'] = pd.to_numeric(df['NET_IMBALANCE_VOLUME'])
        df['IMBALANCE_SETTLEMENT_PRICE'] = pd.to_numeric(df['IMBALANCE_SETTLEMENT_PRICE'])
        df['START_TIME'] = pd.to_datetime(df['START_TIME'])
        return df.sort_values('START_TIME')
    except:
        return None

# --- UI ---
st.title("📊 ISEM NIV & Imbalance Dashboard")
st.caption("Automated alternative to EnAppSys NIV Screen")

# Date Picker (Default to Yesterday)
target_date = st.sidebar.date_input("Trade Date", datetime.now() - timedelta(days=1))

df = get_isem_data(target_date)

if df is not None:
    # Top Stats
    c1, c2, c3 = st.columns(3)
    c1.metric("Avg Imb. Price", f"€{df['IMBALANCE_SETTLEMENT_PRICE'].mean():.2f}")
    c2.metric("Max Long (NIV)", f"{df['NET_IMBALANCE_VOLUME'].max():.1f} MW")
    c3.metric("Max Short (NIV)", f"{df['NET_IMBALANCE_VOLUME'].min():.1f} MW")

    # The EnAppSys Style Chart
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Volume Bars
    colors = ['#EF553B' if x < 0 else '#636EFA' for x in df['NET_IMBALANCE_VOLUME']]
    fig.add_trace(go.Bar(x=df['START_TIME'], y=df['NET_IMBALANCE_VOLUME'], 
                         name="NIV (MW)", marker_color=colors, opacity=0.7), secondary_y=False)
    
    # Price Line
    fig.add_trace(go.Scatter(x=df['START_TIME'], y=df['IMBALANCE_SETTLEMENT_PRICE'], 
                             name="Price (€)", line=dict(color='black', width=2)), secondary_y=True)

    fig.update_layout(hovermode="x unified", legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, use_container_width=True)
    
    st.success(f"Successfully synced with SEM-O for {target_date}")
else:
    st.warning("Data not yet published by SEM-O for this date.")