#!/usr/bin/env python3
"""
IBKR Scanner Dashboard
Real-time view of top gainers, losers, and most active stocks with complete market data
"""

import streamlit as st
import pandas as pd
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
import requests
import os
from dotenv import load_dotenv
from utils.security import safe_markdown_link, sanitize_text
try:
    from fetchers.fetch_news_stocknewsapi import fetch_stocknews_news
except Exception:
    # Fallback if run in different import context
    import sys
    sys.path.append(str(Path(__file__).parent))
    try:
        from fetchers.fetch_news_stocknewsapi import fetch_stocknews_news
    except Exception:
        fetch_stocknews_news = None

load_dotenv()

# Page config
st.set_page_config(
    page_title="IBKR Scanner Dashboard",
    page_icon="📈",
    layout="wide"
)

# Removed custom CSS that required unsafe_allow_html to avoid security warnings.

# Title
st.title("📈 IBKR Scanner Dashboard")
st.markdown("Real-time scanner data with shortable shares, trade rate, and volume metrics")

# Sidebar controls
st.sidebar.header("Scanner Controls")

scan_type = st.sidebar.selectbox(
    "Scanner Type",
    ["after_hours_gainers", "top_gainers", "top_losers", "most_active", "hot_by_volume"],
    index=0
)

limit = st.sidebar.slider("Number of stocks", 10, 100, 50, 10)

# StockNewsAPI controls
st.sidebar.header("StockNewsAPI")
snapi_mode = st.sidebar.selectbox("Ticker match mode", ["any", "include", "only"], index=0,
                                  help="any: articles mention any ticker; include: all tickers in same article; only: only specified ticker(s) mentioned")
snapi_token_default = (
    os.getenv('STOCKNEWS_API_TOKEN')
    or os.getenv('STOCKNEWSAPI_TOKEN')
    or os.getenv('STOCKNEWS_API_KEY')
    or os.getenv('STOCKNEWSAPI_KEY')
)
snapi_token_input = st.sidebar.text_input(
    "Token (optional)", value=snapi_token_default or "", type="password",
    help="Overrides env token if provided"
)
snapi_date_opt = st.sidebar.selectbox("Date filter", ["none", "last7days", "last30days", "custom"], index=0)
snapi_items = st.sidebar.number_input(
    "Items per query",
    min_value=1,
    max_value=100,
    value=100,
    help="Number of headlines to request per StockNewsAPI query"
)
snapi_dt_range = None
snapi_date_val = None
if snapi_date_opt == "custom":
    c1, c2 = st.sidebar.columns(2)
    with c1:
        start_date = st.date_input("Start date")
        start_time = st.text_input("Start time (HHMMSS)", value="160000")
    with c2:
        end_date = st.date_input("End date", value=datetime.now().date())
        end_time = st.text_input("End time (HHMMSS)", value="090000")
    # Compose datetimerange in StockNewsAPI format: MMDDYYYY+HHMMSS-MMDDYYYY+HHMMSS
    try:
        sd = datetime.combine(start_date, datetime.min.time())
        ed = datetime.combine(end_date, datetime.min.time())
        snapi_dt_range = f"{sd.strftime('%m%d%Y')}+{start_time}-{ed.strftime('%m%d%Y')}+{end_time}"
    except Exception:
        snapi_dt_range = None
else:
    if snapi_date_opt in ("last7days", "last30days"):
        snapi_date_val = snapi_date_opt

# Auto-refresh toggle (commented out to prevent flickering)
# auto_refresh = st.sidebar.checkbox("Auto-refresh", value=False)
# refresh_interval = st.sidebar.number_input("Refresh interval (seconds)", 15, 300, 30)

# Load data function
def load_scanner_data():
    """Load scanner data from CSV file"""
    try:
        # Use absolute path to avoid path resolution issues
        base_dir = Path(__file__).parent
        csv_path = base_dir / "output" / "ibkr_scanner_complete.csv"
        
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            return df, None
        else:
            return None, f"CSV file not found at: {csv_path}"
    except Exception as e:
        return None, str(e)

# Fetch fresh data function
def fetch_fresh_scanner_data(scan_type, limit):
    """Fetch fresh scanner data from IBKR"""
    try:
        base_dir = Path(__file__).parent
        # Use live port for after-hours and paper port otherwise
        # Always use paper-trading port 7497 as requested
        ports_to_try = ["7497"]

        last_err = None
        for port in ports_to_try:
            cmd = [
                "python3",
                str(base_dir / "fetchers" / "fetch_ibkr_scanner_complete.py"),
                "--scan-type", scan_type,
                "--limit", str(limit),
                "--port", port
            ]
            result = subprocess.run(
                cmd,
                cwd=str(base_dir),
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode == 0:
                csv_path = base_dir / "output" / "ibkr_scanner_complete.csv"
                df = pd.read_csv(csv_path)
                return df, None
            else:
                last_err = result.stderr
                # Try next port if available
                continue
        return None, last_err or "Unknown error fetching data"
            
    except Exception as e:
        return None, str(e)

# Manual refresh button - fetches fresh data from IBKR
if st.sidebar.button("🔄 Fetch Fresh Data", type="primary", disabled=st.session_state.get('is_fetching', False)):
    # Set fetching state
    if 'is_fetching' not in st.session_state:
        st.session_state.is_fetching = True
        
        with st.spinner(f"Fetching {scan_type} data from IBKR... Please wait..."):
            df_fresh, error = fetch_fresh_scanner_data(scan_type, limit)
        
        st.session_state.is_fetching = False
        
        if error:
            st.sidebar.error(f"Error: {error}")
        else:
            st.sidebar.success("✓ Data fetched successfully!")
            # Clear the Streamlit cache
            st.cache_data.clear()
            time.sleep(0.5)
            st.rerun()

@st.cache_data(ttl=60)
def fetch_finnhub_news(symbols):
    """Fetch news from Finnhub for given symbols"""
    api_key = os.getenv('FINNHUB_API_KEY')
    if not api_key:
        return {}
    
    news_dict = {}
    base_url = 'https://finnhub.io/api/v1/company-news'
    
    # Date range: last 7 days
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    for symbol in symbols:
        try:
            params = {
                'symbol': symbol,
                'from': from_date,
                'to': to_date,
                'token': api_key
            }
            response = requests.get(base_url, params=params, timeout=10)
            
            if response.status_code == 200:
                articles = response.json()
                news_dict[symbol] = articles if isinstance(articles, list) else []
            else:
                news_dict[symbol] = []
                
            time.sleep(0.1)  # Rate limiting
            
        except Exception as e:
            news_dict[symbol] = []
    
    return news_dict

# Load data instantly from CSV
df, error = load_scanner_data()

if error:
    st.error(f"Error loading data: {error}")
    st.info("Click 'Refresh Now' to fetch fresh data from IBKR")
    if st.button("Fetch Fresh Data"):
        with st.spinner(f"Fetching {scan_type} data from IBKR..."):
            df, error = fetch_fresh_scanner_data(scan_type, limit)
        if error:
            st.error(f"Error: {error}")
            st.stop()
        else:
            st.success("Data fetched successfully!")
            st.rerun()
    else:
        st.stop()

if df is None or len(df) == 0:
    st.warning("No data available")
    st.stop()

# Debug: Display loaded columns
with st.expander("🔍 Debug Info"):
    st.write(f"Loaded columns: {list(df.columns)}")
    st.write(f"Has 'change': {'change' in df.columns}")
    st.write(f"Has 'change_pct': {'change_pct' in df.columns}")

# Display timestamp
timestamp_text = df['timestamp'].iloc[0] if 'timestamp' in df.columns else 'Unknown'
st.caption(f"📅 Last updated: {timestamp_text}")

# Summary metrics in columns
col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    st.metric("Total Stocks", len(df))

with col2:
    with_price = df['last_price'].notna().sum()
    st.metric("With Price Data", with_price)

with col3:
    with_shortable = df['shortable_shares'].notna().sum()
    st.metric("Shortable", with_shortable)

with col4:
    avg_volume = df['volume'].mean() if 'volume' in df.columns else 0
    st.metric("Avg Volume", f"{avg_volume:,.0f}")

with col5:
    total_trade_rate = df['trade_rate'].sum() if 'trade_rate' in df.columns else 0
    st.metric("Total Trades/Min", f"{total_trade_rate:,.0f}")

with col6:
    total_news = df['news_count'].sum()
    st.metric("Total News", total_news)

st.divider()

# Filters
st.subheader("Filters")
col1, col2, col3 = st.columns(3)

with col1:
    min_price = st.number_input("Min Price", 0.0, 1000.0, 0.0, 0.1)
    max_price = st.number_input("Max Price", 0.0, 10000.0, 10000.0, 1.0)

with col2:
    min_volume = st.number_input("Min Volume", 0, 10000000, 0, 1000)
    shortable_only = st.checkbox("Shortable only")

with col3:
    min_trade_rate = st.number_input("Min Trade Rate", 0.0, 1000.0, 0.0, 1.0)
    sort_by = st.selectbox("Sort by", ["rank", "volume", "trade_rate", "volume_rate", "shortable_shares", "last_price"])

# Apply filters
filtered_df = df.copy()

if min_price > 0:
    filtered_df = filtered_df[filtered_df['last_price'] >= min_price]
if max_price < 10000:
    filtered_df = filtered_df[filtered_df['last_price'] <= max_price]
if min_volume > 0:
    filtered_df = filtered_df[filtered_df['volume'] >= min_volume]
if shortable_only:
    filtered_df = filtered_df[filtered_df['shortable_shares'].notna()]
if min_trade_rate > 0:
    filtered_df = filtered_df[filtered_df['trade_rate'] >= min_trade_rate]

# Sort
if sort_by != 'rank':
    filtered_df = filtered_df.sort_values(sort_by, ascending=False)

st.divider()

# Main data table
friendly_names = {
    'top_gainers': 'Top % Gainers',
    'after_hours_gainers': 'Top % Gainers',
    'top_losers': 'Top % Losers',
    'most_active': 'Most Active',
    'hot_by_volume': 'Hot by Volume',
    'top_volume': 'Top Volume',
    'hot_by_price': 'Hot by Price',
}
st.subheader(f"{friendly_names.get(scan_type, scan_type.replace('_', ' ').title())} - {len(filtered_df)} stocks")

# Select columns to display - change_pct right after symbol
display_columns = ['rank', 'symbol', 'change_pct', 'last_price', 
                   'volume', 'shortable_shares', 'trade_rate', 'volume_rate', 'news_count', 'latest_news']

# Debug: check if columns exist
if 'change' not in filtered_df.columns:
    st.warning("Note: 'change' column not found in data")
if 'change_pct' not in filtered_df.columns:
    st.warning("Note: 'change_pct' column not found in data")

# Only include columns that exist in the dataframe
display_columns = [col for col in display_columns if col in filtered_df.columns]

# Format the dataframe for display
display_df = filtered_df[display_columns].copy()

# Format columns
if 'last_price' in display_df.columns:
    display_df['last_price'] = display_df['last_price'].apply(lambda x: f"${x:.4f}" if pd.notna(x) else "-")
if 'change' in display_df.columns:
    display_df['change'] = display_df['change'].apply(lambda x: f"${x:+.4f}" if pd.notna(x) else "-")
if 'change_pct' in display_df.columns:
    display_df['change_pct'] = display_df['change_pct'].apply(lambda x: f"{x:+.2f}%" if pd.notna(x) else "-")
if 'volume' in display_df.columns:
    display_df['volume'] = display_df['volume'].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "-")
if 'shortable_shares' in display_df.columns:
    display_df['shortable_shares'] = display_df['shortable_shares'].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "N/A")
if 'trade_rate' in display_df.columns:
    display_df['trade_rate'] = display_df['trade_rate'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "-")
if 'volume_rate' in display_df.columns:
    display_df['volume_rate'] = display_df['volume_rate'].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "-")
if 'news_count' in display_df.columns:
    display_df['news_count'] = display_df['news_count'].apply(lambda x: f"{int(x)}" if pd.notna(x) else "0")
if 'latest_news' in display_df.columns:
    display_df['latest_news'] = display_df['latest_news'].apply(lambda x: (str(x)[:80] + '…') if isinstance(x, str) and len(x) > 80 else (str(x) if pd.notna(x) else "-"))

# Rename columns for better display
display_df = display_df.rename(columns={
    'rank': 'Rank',
    'symbol': 'Symbol',
    'last_price': 'Last',
    'change': 'Change',
    'change_pct': 'Change %',
    'volume': 'Volume',
    'shortable_shares': 'Shortable',
    'trade_rate': 'Trades/Min',
    'volume_rate': 'Vol/Min',
    'news_count': 'News',
    'latest_news': 'Latest News'
})

# Display with styling
st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    height=600
)

# StockNewsAPI News-only update
st.divider()
st.subheader("📰 Update News from StockNewsAPI")
snapi_enabled = fetch_stocknews_news is not None
if not snapi_enabled:
    st.info("StockNewsAPI module not available.")
else:
    if st.button("Fetch News Only (StockNewsAPI)", type="secondary"):
        base_dir = Path(__file__).parent
        csv_path = base_dir / "output" / "ibkr_scanner_complete.csv"
        # Use current filtered df symbols or full df symbols
        symbols = df['symbol'].dropna().astype(str).tolist()
        with st.spinner("Fetching StockNewsAPI news..."):
            try:
                news_map = fetch_stocknews_news(
                    symbols,
                    mode=snapi_mode,
                    items=int(snapi_items),
                    page=1,
                    token=snapi_token_input or None,
                    date=snapi_date_val,
                    datetimerange=snapi_dt_range,
                )
            except Exception as e:
                st.error(f"StockNewsAPI error: {e}")
                news_map = {}

        # Helper to parse existing news_source string
        def parse_source(s: str):
            try:
                parts = {k:0 for k in ['B','PR','S','F']}
                for token in str(s).split():
                    if ':' in token:
                        k,v = token.split(':',1)
                        if k in parts:
                            parts[k] = int(''.join(ch for ch in v if ch.isdigit()))
                return parts
            except Exception:
                return {'B':0,'PR':0,'S':0,'F':0}

        # Load existing articles JSON to merge
        articles_json_path = base_dir / 'output' / 'news_articles.json'
        existing_news = {}
        if articles_json_path.exists():
            try:
                import json
                with open(articles_json_path, 'r') as f:
                    existing_news = json.load(f)
            except Exception:
                existing_news = {}

        # Update df with StockNewsAPI counts and latest headline
        df_updated = df.copy()
        import json
        import pandas as pd
        from datetime import datetime, timedelta
        def is_recent_article(a) -> bool:
            try:
                created = (
                    a.get('created')
                    or a.get('date')
                    or a.get('published_date')
                    or a.get('time')
                    or ''
                )
                if not created:
                    return False
                dt = pd.to_datetime(created, utc=True, errors='coerce')
                if dt is None or str(dt) == 'NaT':
                    return False
                d = dt.date()
                today = datetime.now().date()
                yesterday = today - timedelta(days=1)
                return d == today or d == yesterday
            except Exception:
                return False
        for i, row in df_updated.iterrows():
            sym = str(row.get('symbol',''))
            if not sym:
                continue
            # Filter to only recent (today or yesterday)
            articles_all = news_map.get(sym, [])
            articles = [a for a in articles_all if is_recent_article(a)]
            s_count = len(articles)
            src = parse_source(row.get('news_source','B:0 PR:0 S:0 F:0'))
            src['S'] = s_count
            # Recompute total news count
            total = src['B'] + src['PR'] + src['S'] + src['F']
            df_updated.at[i, 'news_count'] = total
            df_updated.at[i, 'news_source'] = f"B:{src['B']} PR:{src['PR']} S:{src['S']} F:{src['F']}"
            # Prefer StockNewsAPI latest if available
            if s_count > 0:
                df_updated.at[i, 'latest_news'] = articles[0].get('title','No news')
            # Merge articles into JSON storage
            if s_count > 0:
                existing_list = existing_news.get(sym, [])
                merged = articles + existing_list
                # Deduplicate by title+url
                seen = set()
                uniq = []
                for a in merged:
                    key = (a.get('title',''), a.get('url',''))
                    if key in seen:
                        continue
                    seen.add(key)
                    uniq.append(a)
                existing_news[sym] = uniq

        # Save CSV and JSON
        try:
            df_updated.to_csv(csv_path, index=False)
            with open(articles_json_path, 'w') as f:
                json.dump(existing_news, f, indent=2)
            st.success("✓ StockNewsAPI news updated and saved")
            # Refresh view
            st.cache_data.clear()
            time.sleep(0.3)
            st.rerun()
        except Exception as e:
            st.error(f"Unable to save updates: {e}")

# News summary from CSV
if 'news_source' in filtered_df.columns and 'latest_news' in filtered_df.columns:
    st.divider()
    st.subheader("📰 News Summary")
    
    # Show stocks with news
    stocks_with_news = filtered_df[filtered_df['news_count'] > 0]
    
    if len(stocks_with_news) > 0:
        st.write(f"**{len(stocks_with_news)} stocks have news coverage:**")
        
        # Load detailed articles if available
        articles_json_path = Path(__file__).parent / 'output' / 'news_articles.json'
        news_data = {}
        if articles_json_path.exists():
            try:
                import json
                with open(articles_json_path, 'r') as f:
                    news_data = json.load(f)
            except Exception:
                news_data = {}

        for _, row in stocks_with_news.iterrows():
            with st.expander(f"{row['symbol']} - {row['news_count']} articles ({row['news_source']})"):
                from utils.security import sanitize_text
                st.write(f"**Latest headline:** {sanitize_text(row['latest_news'], max_len=300)}")
                st.caption(f"📊 Last Price: ${row['last_price']} | Volume: {row['volume']:,.0f}")
                # List up to 5 articles
                articles = news_data.get(row['symbol'], [])[:5]
                for a in articles:
                    title = a.get('title', 'Untitled')
                    url = a.get('url', '')
                    created = a.get('created', '')
                    source = a.get('source', '')
                    safe_link = safe_markdown_link(title, url)
                    meta = f"{sanitize_text(source)} · {sanitize_text(created)}"
                    st.markdown(f"- {safe_link} · {meta}")
    else:
        st.info("⚠️ **No news found for these stocks**")
        st.write("""
        Small-cap/penny stocks often lack news coverage in APIs. News may be available for:
        - **Larger cap stocks** (e.g., run scanner on most_active instead of top_gainers)
        - **During market hours** with breaking news
        - **Premium Benzinga subscription** (Pro tier)
        
        💡 **Tip:** The news you see on Benzinga's website may not be available via their API.
        """)

# Detailed view in expander
with st.expander("📊 Full Details (All Columns)"):
    # Drop news_articles column only if it exists
    cols_to_drop = ['news_articles'] if 'news_articles' in filtered_df.columns else []
    df_to_show = filtered_df.drop(columns=cols_to_drop) if cols_to_drop else filtered_df
    st.dataframe(df_to_show, use_container_width=True, hide_index=True)

# Download button
cols_to_drop = ['news_articles'] if 'news_articles' in filtered_df.columns else []
df_to_export = filtered_df.drop(columns=cols_to_drop) if cols_to_drop else filtered_df
csv = df_to_export.to_csv(index=False)
st.download_button(
    label="📥 Download CSV",
    data=csv,
    file_name=f"ibkr_scanner_{scan_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
    mime="text/csv"
)

# Auto-refresh (disabled to prevent flickering)
# if auto_refresh:
#     time.sleep(refresh_interval)
#     st.rerun()

# Footer
st.divider()
st.caption("💡 Tip: Enable auto-refresh to monitor real-time scanner data during market hours")
st.caption("⚠️ Note: Some stocks may not have shortable shares available (shows N/A)")
