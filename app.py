import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# --- 1. INITIAL SETTINGS ---
st.set_page_config(page_title="ISEM Market Terminal", layout="wide", page_icon="⚡")

# Initialize variables to prevent "NameError" if API fails entirely
df = None
mode = "Search"
actual_date = None

# Helper to parse SEM-O XML safely
def parse_sem_xml(content):
    try:
        root = ET.fromstring(content)
        rows = []
        for row in root.findall('.//Row'):
            rows.append({child.tag: child.text for child in row})
        return pd.DataFrame(rows)
    except Exception as e:
        return None

# --- 2. THE DATA ENGINE (No Guessing Timestamps) ---
@st.cache_data(ttl=600)
def get_isem_data_safely(target_date):
    # Act like a normal web browser to prevent 403 Forbidden / Bot blocks
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    # The dedicated API for finding static file names
    search_api_url = "https://reports.sem-o.com/api/v1/documents/static-reports"
    
    # Look back up to 5 days to find the most recent finalized data
    for i in range(6):
        check_date = target_date - timedelta(days=i)
        
        params = {
            'ReportName': 'Imbalance Price Report (Imbalance Settlement Period)',
            'Date': check_date.strftime('%Y-%m-%d'),
            'page_size': 10
        }
        
        try:
            # 1. Ask the API for the exact list of files published on this date
            r = requests.get(search_api_url, params=params, headers=headers, timeout=10)
            
            if r.status_code == 200:
                items = r.json().get('items', [])
                
                if items:
                    # 2. Grab the exact filename of the most recent file (e.g., PUB_..._1704.xml)
                    resource_name = items[0]['ResourceName']
                    doc_url = f"https://reports.sem-o.com/documents/{resource_name}"
                    
                    # 3. Download the actual XML document
                    data_r = requests.get(doc_url, headers=headers, timeout=10)
                    
                    if data_r.status_code == 200:
                        data = parse_sem_xml(data_r.content)
                        if data is not None and not data.empty:
                            return data, "Official Settlement", check_date
        except Exception:
            continue # Silently move to the next day if connection drops
            
    return None, None, None

# --- 3. UI & CONTROLS ---
st.title("🇮🇪 ISEM NIV & Price Terminal")
st.markdown("Automated sync with SEM-O via Static API routing.")

with st.sidebar:
    st.header("Terminal Settings")
    user_date = st.date_input("Analysis Date", datetime.now())
    st.divider()
    st.info("Status: Checking SEM-O API for exact file signatures.")

# Execute Data Fetch
df, mode, actual_date = get_isem_data_safely(user_date)

# --- 4. DATA PROCESSING & VISUALIZATION ---
if df is not None and not df.empty:
    
    # FLEXIBLE COLUMN SNIFFER (Adapts to whatever SEM-O names the columns today)
    p_col = next((c for c in ['IMBALANCE_SETTLEMENT_PRICE', 'IMBALANCE_PRICE', 'NET_IMBALANCE_PRICE'] if c in df.columns), None)
    v_col = next((c for c in ['NET_IMBALANCE_VOLUME', 'QNIV', 'VOLUME'] if c in df.columns), None)
    t_col = 'START_TIME'

    if p_col and v_col:
        # Clean Data
        df[p_col] = pd.to_numeric(df[p_col], errors='coerce')
        df[v_col] = pd.to_numeric(df[v_col], errors='coerce')
        df[t_col] = pd.to_datetime(df[t_col])
        df = df.dropna(subset=[p_col, v_col]).sort_values(t_col)

        # Alerts & Headers
        if actual_date != user_date:
            st.warning(f"Data for {user_date.strftime('%d %b')} is not ready. Showing most recent: **{actual_date.strftime('%d %b %Y')}**")
        else:
            st.success(f"Displaying data for: **{actual_date.strftime('%d %b %Y')}**")
            
        # Metric Cards
        c1, c2, c3 = st.columns(3)
        c1.metric("Avg Price", f"€{df[p_col].mean():.2f}")
        c2.metric("Max System Long", f"{df[v_col].max():.0f} MW")
        c3.metric("Max System Short", f"{df[v_col].min():.0f} MW")

        # The Chart
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        colors = ['#EF553B' if x < 0 else '#636EFA' for x in df[v_col]]
        
        fig.add_trace(go.Bar(x=df[t_col], y=df[v_col], name="NIV (MW)", marker_color=colors), secondary_y=False)
        fig.add_trace(go.Scatter(x=df[t_col], y=df[p_col], name="Price (€)", line=dict(color='black', width=2)), secondary_y=True)
        
        fig.update_layout(hovermode="x unified", height=500, margin=dict(t=30, b=10))
        fig.update_yaxes(title_text="<b>NIV</b> (MW)", secondary_y=False)
        fig.update_yaxes(title_text="<b>Price</b> (€/MWh)", secondary_y=True)
        st.plotly_chart(fig, use_container_width=True)

        # Raw Data Output
        with st.expander("Raw Data Inspection"):
            st.write(df)
            
            # Bonus: Download to CSV Button
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download data as CSV",
                data=csv,
                file_name=f"ISEM_NIV_{actual_date.strftime('%Y%m%d')}.csv",
                mime='text/csv',
            )
    else:
        st.error(f"Columns not found. SEM-O may have updated their format. Found columns: {df.columns.tolist()}")
else:
    st.error("SYSTEM ALERT: No data found. SEM-O Balancing Market Interface may be down for scheduled maintenance (Check Outages for Feb 16).")