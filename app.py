import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# --- CONFIG ---
st.set_page_config(page_title="ISEM NIV Terminal", layout="wide", page_icon="📈")

# This function now "hunts" for the most recent available data
@st.cache_data(ttl=3600)
def get_isem_data(start_date):
    REPORT_LIST_URL = "https://reports.sem-o.com/api/v1/dynamic/reports"
    doc_url_base = "https://reports.sem-o.com/documents/"
    
    # Check selected date, then go back up to 5 days if data is missing
    for i in range(6): 
        check_date = start_date - timedelta(days=i)
        params = {
            'ReportName': 'Imbalance Price Report (Imbalance Settlement Period)',
            'Date': check_date.strftime('%Y-%m-%d'),
            'page_size': 5
        }
        
        try:
            r = requests.get(report_list_url, params=params, timeout=10)
            items = r.json().get('items', [])
            
            if items:
                resource = items[0]['ResourceName']
                data_r = requests.get(f"{doc_url_base}{resource}", timeout=10)
                root = ET.fromstring(data_r.content)
                
                rows = []
                for row in root.findall('.//Row'):
                    rows.append({child.tag: child.text for child in row})
                
                df = pd.DataFrame(rows)
                # Data Cleaning
                df['NET_IMBALANCE_VOLUME'] = pd.to_numeric(df['NET_IMBALANCE_VOLUME'])
                df['IMBALANCE_SETTLEMENT_PRICE'] = pd.to_numeric(df['IMBALANCE_SETTLEMENT_PRICE'])
                df['START_TIME'] = pd.to_datetime(df['START_TIME'])
                return df.sort_values('START_TIME'), check_date
        except Exception:
            continue
            
    return None, None

# --- UI HEADER ---
st.title("📊 ISEM Market Intelligence")
st.markdown("### Net Imbalance Volume (NIV) & Settlement Price")

# Sidebar for manual date override
with st.sidebar:
    st.header("Controls")
    user_date = st.date_input("Target Date", datetime.now() - timedelta(days=1))
    st.divider()
    st.info("The app automatically finds the most recent finalized report if your target date isn't ready.")

# --- DATA EXECUTION ---
df, actual_date = get_isem_data(user_date)

if df is not None:
    # Status Banner
    if actual_date != user_date:
        st.warning(f"Data for {user_date} is not yet published. Showing most recent: **{actual_date.strftime('%d %b %Y')}**")
    else:
        st.success(f"Displaying data for: **{actual_date.strftime('%d %b %Y')}**")

    # 1. Key Metrics Row
    c1, c2, c3, c4 = st.columns(4)
    avg_price = df['IMBALANCE_SETTLEMENT_PRICE'].mean()
    total_short = df[df['NET_IMBALANCE_VOLUME'] < 0]['NET_IMBALANCE_VOLUME'].sum()
    total_long = df[df['NET_IMBALANCE_VOLUME'] > 0]['NET_IMBALANCE_VOLUME'].sum()
    
    c1.metric("Avg Imbalance Price", f"€{avg_price:.2f}")
    c2.metric("System Short (Total MW)", f"{abs(total_short):.1f}", delta_color="inverse")
    c3.metric("System Long (Total MW)", f"{total_long:.1f}")
    c4.metric("Reporting Intervals", f"{len(df)}")

    # 2. The Professional Chart
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Custom colors for NIV (Short = Red, Long = Blue)
    colors = ['#EF553B' if x < 0 else '#636EFA' for x in df['NET_IMBALANCE_VOLUME']]

    fig.add_trace(
        go.Bar(x=df['START_TIME'], y=df['NET_IMBALANCE_VOLUME'], 
               name="NIV (MW)", marker_color=colors, opacity=0.6),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(x=df['START_TIME'], y=df['IMBALANCE_SETTLEMENT_PRICE'], 
                   name="Price (€/MWh)", line=dict(color='black', width=2.5)),
        secondary_y=True,
    )

    fig.update_layout(
        height=600,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=0, r=0, t=40, b=0)
    )

    fig.update_yaxes(title_text="<b>NIV Volume</b> (MW)", secondary_y=False)
    fig.update_yaxes(title_text="<b>Settlement Price</b> (€)", secondary_y=True)

    st.plotly_chart(fig, use_container_width=True)

    # 3. Data Table
    with st.expander("Inspection: Raw Settlement Data"):
        st.dataframe(df.style.background_gradient(subset=['NET_IMBALANCE_VOLUME'], cmap='RdBu'))

else:
    st.error("Unable to retrieve any data from SEM-O for the last 5 days. Please check the market operator's status.")

# Footer
st.divider()
st.caption(f"Last sync attempted at: {datetime.now().strftime('%H:%M:%S')}")