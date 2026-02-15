if df is not None:
    # 1. STANDARDIZE PRICE COLUMN (Sniff out the correct name)
    possible_price_cols = ['IMBALANCE_SETTLEMENT_PRICE', 'IMBALANCE_PRICE', 'NET_IMBALANCE_PRICE']
    found_price_col = next((col for col in possible_price_cols if col in df.columns), None)
    
    # 2. STANDARDIZE VOLUME COLUMN
    possible_vol_cols = ['NET_IMBALANCE_VOLUME', 'QNIV', 'VOLUME']
    found_vol_col = next((col for col in possible_vol_cols if col in df.columns), None)

    if found_price_col and found_vol_col:
        # Convert to numbers and handle the "None" or blank strings
        df[found_price_col] = pd.to_numeric(df[found_price_col], errors='coerce')
        df[found_vol_col] = pd.to_numeric(df[found_vol_col], errors='coerce')
        df['START_TIME'] = pd.to_datetime(df['START_TIME'])
        df = df.dropna(subset=[found_price_col, found_vol_col]) # Remove empty rows
        df = df.sort_values('START_TIME')

        # If we are in 5-min Indicative mode, we aggregate to 30-min
        if mode == "Indicative":
            df = df.resample('30T', on='START_TIME').agg({
                found_vol_col: 'sum', 
                found_price_col: 'mean'
            }).reset_index()
    else:
        st.error(f"Data format error: Found columns {df.columns.tolist()}. Expected price/volume columns.")
        st.stop()