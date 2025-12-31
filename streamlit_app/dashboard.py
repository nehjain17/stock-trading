#!/usr/bin/env python3
"""
Stock Trading Dashboard
Displays real-time data and news for short squeeze candidates
"""
import streamlit as st
import pandas as pd
import os
from datetime import datetime
import glob
from utils.security import safe_markdown_link, sanitize_text

# Page config
st.set_page_config(
    page_title="Stock Trading Dashboard",
    page_icon="📈",
    layout="wide"
)

@st.cache_data(ttl=60)
def load_data_file(filepath):
    """Load CSV data with caching"""
    if os.path.exists(filepath):
        return pd.read_csv(filepath)
    return pd.DataFrame()

@st.cache_data(ttl=300)
def load_all_data():
    """Load all data files"""
    data = {}
    
    # Market data sources
    data['ibkr'] = load_data_file('output/ibkr_market_data.csv')
    data['moomoo'] = load_data_file('output/moomoo_market_data.csv')
    data['yahoo'] = load_data_file('output/yahoo_market_data.csv')
    
    # News sources
    data['benzinga_news'] = load_data_file('output/benzinga_news.csv')
    data['finnhub_news'] = load_data_file('output/finnhub_news.csv')
    
    # Combine market data (prioritize IBKR > Moomoo > Yahoo)
    market_data = pd.DataFrame()
    for source in ['ibkr', 'moomoo', 'yahoo']:
        if not data[source].empty:
            if market_data.empty:
                market_data = data[source].copy()
            else:
                # Merge, keeping existing data and filling gaps
                market_data = market_data.merge(
                    data[source],
                    on='symbol',
                    how='outer',
                    suffixes=('', f'_{source}')
                )
    
    data['market'] = market_data
    
    # Combine news
    news_data = pd.concat([data['benzinga_news'], data['finnhub_news']], ignore_index=True)
    if not news_data.empty:
        news_data = news_data.drop_duplicates(subset=['symbol', 'title'])
        news_data = news_data.sort_values('timestamp', ascending=False)
    data['news'] = news_data
    
    return data

def calculate_squeeze_score(row):
    """Calculate short squeeze potential score"""
    score = 0
    
    # High volume spike
    if pd.notna(row.get('volume')) and pd.notna(row.get('avg_volume')):
        if row['volume'] > row['avg_volume'] * 2:
            score += 30
        elif row['volume'] > row['avg_volume'] * 1.5:
            score += 20
    
    # Short interest
    if pd.notna(row.get('short_percent_float')):
        if row['short_percent_float'] > 20:
            score += 30
        elif row['short_percent_float'] > 10:
            score += 20
    
    # Low float
    if pd.notna(row.get('float_shares')) and pd.notna(row.get('market_cap')):
        if row['float_shares'] < 10_000_000:
            score += 25
        elif row['float_shares'] < 50_000_000:
            score += 15
    
    # Price action
    if pd.notna(row.get('last_price')) and pd.notna(row.get('low')):
        day_range = (row['last_price'] - row['low']) / row['low'] * 100
        if day_range > 10:
            score += 15
    
    return score

# Main UI
st.title("📈 Stock Trading Dashboard")
st.markdown("**Real-time data for short squeeze candidates**")

# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    
    # Data refresh
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    # Filters
    st.subheader("Filters")
    min_volume = st.number_input("Min Volume", value=100000, step=10000)
    min_squeeze_score = st.slider("Min Squeeze Score", 0, 100, 50)
    show_news_only = st.checkbox("Show stocks with news only", value=False)
    
    # Source files info
    st.subheader("📁 Source Files")
    source_files = glob.glob("input/low_float_stocks_*.csv")
    if source_files:
        for f in source_files:
            st.text(f"• {os.path.basename(f)}")
    st.text("• all_stocks_complete.csv")

# Load data
data = load_all_data()
market = data['market']
news = data['news']

# Stats row
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Stocks", len(market) if not market.empty else 0)

with col2:
    st.metric("News Items", len(news) if not news.empty else 0)

with col3:
    active_sources = sum([
        not data['ibkr'].empty,
        not data['moomoo'].empty,
        not data['yahoo'].empty
    ])
    st.metric("Active Data Sources", active_sources)

with col4:
    if not market.empty:
        last_update = market['timestamp'].max() if 'timestamp' in market.columns else 'N/A'
        st.metric("Last Update", last_update)

st.divider()

# Main content tabs
tab1, tab2, tab3 = st.tabs(["🎯 Top Candidates", "📰 Latest News", "📊 All Stocks"])

with tab1:
    st.subheader("Short Squeeze Candidates")
    
    if market.empty:
        st.warning("No market data available. Run data fetchers first.")
        st.code("""
# Fetch data:
python fetch_data_yahoo.py --input low_float_stocks_100M.csv --limit 100
python fetch_news_benzinga.py --input low_float_stocks_100M.csv --limit 100
        """)
    else:
        # Calculate squeeze scores
        market['squeeze_score'] = market.apply(calculate_squeeze_score, axis=1)
        
        # Apply filters
        filtered = market.copy()
        if 'volume' in filtered.columns:
            filtered = filtered[filtered['volume'] >= min_volume]
        filtered = filtered[filtered['squeeze_score'] >= min_squeeze_score]
        
        if show_news_only and not news.empty:
            filtered = filtered[filtered['symbol'].isin(news['symbol'])]
        
        # Sort by score
        filtered = filtered.sort_values('squeeze_score', ascending=False)
        
        st.write(f"**{len(filtered)} stocks match criteria**")
        
        # Display top candidates
        for idx, row in filtered.head(20).iterrows():
            with st.expander(f"**{row['symbol']}** - Score: {row['squeeze_score']:.0f}"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Last Price", f"${row.get('last_price', 0):.2f}")
                    st.metric("Volume", f"{row.get('volume', 0):,.0f}")
                
                with col2:
                    st.metric("Float", f"{row.get('float_shares', 0):,.0f}")
                    st.metric("Market Cap", f"${row.get('market_cap', 0):,.0f}")
                
                with col3:
                    st.metric("Short %", f"{row.get('short_percent_float', 0):.1f}%")
                    st.metric("Day Range", f"{((row.get('high', 0) - row.get('low', 1)) / row.get('low', 1) * 100):.1f}%")
                
                # Show news for this stock
                if not news.empty:
                    stock_news = news[news['symbol'] == row['symbol']].head(3)
                    if not stock_news.empty:
                        st.markdown("**Recent News:**")
                        for _, news_row in stock_news.iterrows():
                            link = safe_markdown_link(news_row.get('title', ''), news_row.get('url', ''))
                            source = sanitize_text(news_row.get('source', ''))
                            st.markdown(f"• {link} - *{source}*")

with tab2:
    st.subheader("Latest News")
    
    if news.empty:
        st.info("No news data available. Run news fetchers first.")
    else:
        # Filter by symbols in market data
        if not market.empty:
            news_filtered = news[news['symbol'].isin(market['symbol'])]
        else:
            news_filtered = news
        
        st.write(f"**{len(news_filtered)} news items**")
        
        # Display news
        for idx, row in news_filtered.head(50).iterrows():
            link = safe_markdown_link(row.get('title', ''), row.get('url', ''))
            symbol = sanitize_text(row.get('symbol', ''))
            st.markdown(f"**{symbol}** - {link}")
            st.caption(f"{sanitize_text(row.get('source', ''))} | {sanitize_text(row.get('timestamp', ''))}")
            st.divider()

with tab3:
    st.subheader("All Stocks")
    
    if market.empty:
        st.info("No data available")
    else:
        # Prepare display dataframe
        display_cols = ['symbol', 'last_price', 'volume', 'market_cap', 
                       'float_shares', 'short_percent_float', 'squeeze_score']
        display_df = market[[c for c in display_cols if c in market.columns]].copy()
        
        # Format numbers
        if 'last_price' in display_df.columns:
            display_df['last_price'] = display_df['last_price'].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "")
        if 'volume' in display_df.columns:
            display_df['volume'] = display_df['volume'].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "")
        if 'market_cap' in display_df.columns:
            display_df['market_cap'] = display_df['market_cap'].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "")
        if 'float_shares' in display_df.columns:
            display_df['float_shares'] = display_df['float_shares'].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "")
        
        st.dataframe(display_df, use_container_width=True, height=600)
        
        # Download button
        csv = market.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"market_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

# Footer
st.divider()
st.caption("💡 Tip: Run fetchers regularly to keep data updated. Use --limit flag to test with small batches first.")
