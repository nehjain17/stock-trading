#!/usr/bin/env python3
"""
Stock News Dashboard - Combined view of stocks and news
"""
import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import pytz

# Page config
st.set_page_config(
    page_title="Stock News Dashboard",
    page_icon="📰",
    layout="wide"
)

# Custom CSS to reduce sidebar width and optimize layout
st.markdown("""
    <style>
    /* Reduce sidebar width */
    [data-testid="stSidebar"][aria-expanded="true"] {
        min-width: 200px;
        max-width: 200px;
    }
    [data-testid="stSidebar"][aria-expanded="false"] {
        min-width: 200px;
        max-width: 200px;
        margin-left: -200px;
    }
    /* Optimize main content area */
    .main .block-container {
        max-width: 100%;
        padding-left: 1rem;
        padding-right: 1rem;
        padding-top: 1rem;
        padding-bottom: 1rem;
    }
    /* Make dataframe use full width */
    div[data-testid="stDataFrame"] {
        width: 100%;
    }
    /* Reduce sidebar top padding */
    .css-1d391kg, [data-testid="stSidebar"] > div:first-child {
        padding-top: 0.5rem;
    }
    /* Reduce spacing in sidebar */
    [data-testid="stSidebar"] .element-container {
        margin-bottom: 0.3rem;
    }
    [data-testid="stSidebar"] h1 {
        font-size: 1.3rem;
        margin-bottom: 0.5rem;
        margin-top: 0.5rem;
    }
    [data-testid="stSidebar"] h3 {
        font-size: 1rem;
        margin-bottom: 0.3rem;
        margin-top: 0.5rem;
    }
    [data-testid="stSidebar"] hr {
        margin: 0.5rem 0;
    }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=60)  # Cache for 1 minute
def load_stock_data():
    """Load stock fundamental data"""
    try:
        df = pd.read_csv('all_stocks_complete.csv')
        return df
    except Exception as e:
        st.error(f"Error loading stock data: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=30)  # Cache for 30 seconds
def load_news_data(source=None, hours=24):
    """Load news from database"""
    try:
        conn = sqlite3.connect('news_cache.db')
        
        query = '''
            SELECT 
                symbol, 
                headline, 
                summary, 
                source, 
                url, 
                published_at,
                is_catalyst,
                sentiment
            FROM news
            WHERE published_at >= ?
        '''
        params = [(datetime.now() - timedelta(hours=hours)).isoformat()]
        
        if source:
            query += ' AND source = ?'
            params.append(source)
        
        query += ' ORDER BY published_at DESC'
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        # Convert published_at to datetime with mixed format support, then remove timezone
        df['published_at'] = pd.to_datetime(df['published_at'], format='mixed', utc=True).dt.tz_localize(None)
        
        return df
    except Exception as e:
        st.error(f"Error loading news: {e}")
        return pd.DataFrame()

def merge_stock_news(stocks_df, news_df):
    """Merge stock data with ALL news items (not just latest)"""
    if news_df.empty:
        return pd.DataFrame()
    
    # Select available columns from stock data
    available_cols = ['symbol', 'name', 'market_cap', 'float_shares']
    if 'share_outstanding' in stocks_df.columns:
        available_cols.append('share_outstanding')
    
    # Merge ALL news with stock data
    merged = news_df.merge(
        stocks_df[available_cols],
        on='symbol',
        how='left'
    )
    
    # Convert published_at to timezone-naive for calculation
    if merged['published_at'].dt.tz is not None:
        merged['published_at'] = merged['published_at'].dt.tz_localize(None)
    
    # Calculate time since news
    merged['hours_ago'] = (datetime.now() - merged['published_at']).dt.total_seconds() / 3600
    merged['hours_ago'] = merged['hours_ago'].round(1)
    
    # Sort by published time (most recent first)
    merged = merged.sort_values('published_at', ascending=False)
    
    return merged

def format_market_cap(value):
    """Format market cap for display"""
    if pd.isna(value):
        return "N/A"
    if value >= 1e12:
        return f"${value/1e12:.2f}T"
    elif value >= 1e9:
        return f"${value/1e9:.2f}B"
    elif value >= 1e6:
        return f"${value/1e6:.2f}M"
    else:
        return f"${value:,.0f}"

def format_volume(value):
    """Format volume for display"""
    if pd.isna(value):
        return "N/A"
    if value >= 1e9:
        return f"{value/1e9:.2f}B"
    elif value >= 1e6:
        return f"{value/1e6:.2f}M"
    elif value >= 1e3:
        return f"{value/1e3:.2f}K"
    else:
        return f"{value:,.0f}"

# Sidebar
st.sidebar.title("📰 News Dashboard")

# View selection - clickable menu items
st.sidebar.subheader("Views")

# Initialize session state for selected view
if 'selected_view' not in st.session_state:
    st.session_state.selected_view = "Finnhub News"

# Create clickable menu items
views = [
    "Finnhub News", 
    "All News", 
    "Low Float < 10M",
    "Low Float < 50M",
    "Low Float < 100M",
    "High Volume Stocks",
    "Benzinga News"
]
for view_name in views:
    if st.sidebar.button(
        view_name, 
        key=f"btn_{view_name}",
        use_container_width=True,
        type="primary" if st.session_state.selected_view == view_name else "secondary"
    ):
        st.session_state.selected_view = view_name

view = st.session_state.selected_view

# Time filter - default to 7 days for low float views since they have less frequent news
default_time_index = 4 if view.startswith("Low Float") else 2
time_filter = st.sidebar.selectbox(
    "News Time Range",
    [6, 12, 24, 48, 168],
    index=default_time_index,
    format_func=lambda x: f"Last {x} hours" if x < 168 else "Last 7 days"
)

# Filters
st.sidebar.subheader("Filters")

# Search filter
search_term = st.sidebar.text_input(
    "🔍 Search Symbol or Name",
    value="",
    placeholder="e.g., AAPL or Apple",
    help="Filter stocks by symbol or company name"
).strip().upper()

min_market_cap = st.sidebar.number_input(
    "Min Market Cap ($M)",
    min_value=0,
    value=0,
    step=100
)

show_catalysts_only = st.sidebar.checkbox("Catalyst News Only", value=False)

# Load data
stocks_df = load_stock_data()

# Main content - compact header
st.markdown(f"### 📰 Stock News Dashboard")

# Display based on view
if view == "Benzinga News":
    news_df = load_news_data(source='Benzinga', hours=time_filter)
    
elif view == "Finnhub News":
    news_df = load_news_data(source='Finnhub', hours=time_filter)
    
elif view == "All News":
    news_df = load_news_data(hours=time_filter)

elif view.startswith("Low Float"):
    # Extract float threshold from view name
    if "< 10M" in view:
        float_threshold = 10e6
    elif "< 50M" in view:
        float_threshold = 50e6
    elif "< 100M" in view:
        float_threshold = 100e6
    else:
        float_threshold = 10e6
    
    # Filter stocks by float
    if 'float_shares' in stocks_df.columns:
        stocks_df = stocks_df[stocks_df['float_shares'] < float_threshold]
    
    news_df = load_news_data(hours=time_filter)
    
else:  # High Volume Stocks
    news_df = load_news_data(hours=time_filter)

# Apply filters
if show_catalysts_only and not news_df.empty:
    news_df = news_df[news_df['is_catalyst'] == 1]

# Merge and display
if not news_df.empty and not stocks_df.empty:
    merged_df = merge_stock_news(stocks_df, news_df)
    
    # For low float views, only show news for stocks that are actually in the filtered stocks_df
    if view.startswith("Low Float"):
        merged_df = merged_df[merged_df['name'].notna()]
    
    # Apply search filter
    if search_term:
        merged_df = merged_df[
            merged_df['symbol'].str.contains(search_term, case=False, na=False) |
            merged_df['name'].str.contains(search_term, case=False, na=False)
        ]
    
    # Apply market cap filter
    if min_market_cap > 0:
        merged_df = merged_df[merged_df['market_cap'] >= min_market_cap * 1e6]
    
    # Apply catalyst filter
    if show_catalysts_only:
        merged_df = merged_df[merged_df['is_catalyst'] == 1]
    
    # Sort based on view
    if view == "High Volume Stocks":
        # Sort by float shares or shares outstanding as proxy for volume
        if 'float_shares' in merged_df.columns:
            merged_df = merged_df.sort_values('float_shares', ascending=False, na_position='last')
            st.info(f"**Note:** Sorted by float shares (volume data not available)")
        elif 'share_outstanding' in merged_df.columns:
            merged_df = merged_df.sort_values('share_outstanding', ascending=False, na_position='last')
            st.info(f"**Note:** Sorted by shares outstanding (volume data not available)")
        else:
            merged_df = merged_df.sort_values('published_at', ascending=False)
            st.warning("Volume/share data not available - showing by latest news")
    else:
        merged_df = merged_df.sort_values('published_at', ascending=False)
    
    # Compact summary stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Stocks", len(merged_df))
    with col2:
        st.metric("News", len(news_df))
    with col3:
        catalysts = merged_df['is_catalyst'].sum() if 'is_catalyst' in merged_df else 0
        st.metric("Catalysts", int(catalysts))
    with col4:
        sources = news_df['source'].nunique() if not news_df.empty else 0
        st.metric("Sources", sources)
    
    # Display table
    if len(merged_df) > 0:
        # Download option at top
        csv = merged_df.to_csv(index=False)
        st.download_button(
            label="📥 CSV",
            data=csv,
            file_name=f"stock_news_{view.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
        
        # Prepare display dataframe with available columns
        display_cols = ['symbol', 'name', 'headline', 'source', 'published_at', 'hours_ago', 'market_cap']
        
        # Add float_shares if available
        if 'float_shares' in merged_df.columns:
            display_cols.append('float_shares')
        
        display_cols.extend(['is_catalyst', 'url'])
        
        display_df = merged_df[display_cols].copy()
        
        # Format columns
        display_df['market_cap'] = display_df['market_cap'].apply(format_market_cap)
        if 'float_shares' in display_df.columns:
            display_df['float_shares'] = display_df['float_shares'].apply(format_volume)
        display_df['published_at'] = display_df['published_at'].dt.strftime('%Y-%m-%d %H:%M')
        display_df['is_catalyst'] = display_df['is_catalyst'].map({1: '🔥', 0: ''})
        
        # Rename columns
        col_names = ['Symbol', 'Name', 'Headline', 'Source', 'Published', 'Hours Ago', 'Market Cap']
        if 'float_shares' in display_df.columns:
            col_names.append('Float Shares')
        col_names.extend(['Catalyst', 'URL'])
        
        display_df.columns = col_names
        
        # Display table with large height to fill viewport with own scrollbar
        st.dataframe(
            display_df,
            use_container_width=True,
            height=800,
            column_config={
                "URL": st.column_config.LinkColumn("URL"),
                "Headline": st.column_config.TextColumn("Headline", width="large"),
                "Symbol": st.column_config.TextColumn("Symbol", width="small"),
                "Name": st.column_config.TextColumn("Name", width="medium"),
            },
            hide_index=True
        )
    else:
        st.warning("No stocks match the current filters")
else:
    st.warning("No news data available. Make sure the news monitor is running.")
    st.info("Start the news monitor with: `./start_news_monitor.sh`")

# Refresh button
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# Footer
st.sidebar.markdown("---")
st.sidebar.markdown("### About")
st.sidebar.info(
    "This dashboard combines stock fundamental data with real-time news from "
    "Benzinga and Finnhub. News is automatically updated every 5 minutes."
)
