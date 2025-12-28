import streamlit as st
import pandas as pd
from datetime import datetime
import asyncio
import os
from dotenv import load_dotenv
import requests

# Ensure an asyncio event loop exists for Streamlit's script thread.
try:
    asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        import nest_asyncio
        nest_asyncio.apply(loop)
    except Exception:
        pass

# Helper to run a coroutine whether the current loop is running or not.
def run_async_coroutine(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()
    else:
        return loop.run_until_complete(coro)

import time
from ib_insync import IB, Stock

# We'll dynamically fetch symbols from Finnhub (or allow manual input).
def fetch_symbols_from_finnhub(exchange='US', limit=250):
    """Fetch a list of symbols from Finnhub. Returns up to `limit` symbols or [] on error."""
    key = os.getenv('FINNHUB_API_KEY')
    if not key:
        st.warning('No FINNHUB_API_KEY found in .env — switch to Manual input or add your key.')
        return []

    url = 'https://finnhub.io/api/v1/stock/symbol'
    params = {'exchange': exchange, 'token': key}
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        symbols = [item.get('symbol') for item in data if item.get('symbol')]
        return symbols[:limit]
    except Exception as e:
        st.warning(f'Finnhub symbol fetch failed: {e}')
        return []


# Load environment variables
load_dotenv()

# Keys - Load from .env file
IBKR_HOST = os.getenv('IBKR_HOST', '127.0.0.1')
IBKR_PORT = int(os.getenv('IBKR_PORT', 7497))
IBKR_CLIENT_ID = int(os.getenv('IBKR_CLIENT_ID', 1))

# IBKR Connection (Read-Only)
async def connect_ibkr():
    """Connect to Interactive Brokers in read-only mode"""
    try:
        ib = IB()
        ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID, readonly=True)
        await asyncio.sleep(0.5)
        return ib
    except Exception as e:
        st.error(f"IBKR Connection Error: {e}. Ensure TWS is running with Read-Only API enabled.")
        return None

# Get shortable shares for a stock
async def get_shortable_shares(ib, ticker):
    """Fetch shortable shares for a stock"""
    try:
        import math
        contract = Stock(ticker, 'SMART', 'USD')
        
        # Request market data which includes shortable shares
        ib.reqMarketDataType(4)  # Delayed data
        ib.reqMktData(contract, '', False, False)  # Streaming market data
        await asyncio.sleep(1.5)  # Wait for data to arrive
        
        # Get the ticker object which contains shortable info
        ticker_obj = ib.ticker(contract)
        shortable = ticker_obj.shortableShares if hasattr(ticker_obj, 'shortableShares') else None
        
        # Handle NaN values
        if shortable is None or (isinstance(shortable, float) and math.isnan(shortable)):
            shortable = 0
        else:
            try:
                shortable = int(shortable)
            except (ValueError, TypeError):
                shortable = 0
        
        # Cancel market data subscription
        try:
            ib.cancelMktData(contract)
        except:
            pass
        
        return {
            'Ticker': ticker,
            'Shortable Shares': shortable
        }
    except Exception as e:
        pass  # Silently skip on error
        return None

# Scanner for shortable shares < 20000
def scan_shortable(tickers):
    """Scan stocks for shortable shares < 20000"""
    try:
        async def run_scan():
            ib = await connect_ibkr()
            if not ib:
                return pd.DataFrame()
            
            results = []
            progress_bar = st.progress(0)
            
            for idx, ticker in enumerate(tickers):
                try:
                    data = await get_shortable_shares(ib, ticker)
                    if not data:
                        progress_bar.progress((idx + 1) / len(tickers))
                        continue
                    
                    # Filter: Include stocks with shortable shares < 20000 (including 0)
                    if data['Shortable Shares'] < 20000:
                        results.append(data)
                    
                    progress_bar.progress((idx + 1) / len(tickers))
                except Exception as e:
                    st.warning(f"Error processing {ticker}: {e}")
                    progress_bar.progress((idx + 1) / len(tickers))
            
            try:
                ib.disconnect()
            except:
                pass
            
            return pd.DataFrame(results)
        
        return run_async_coroutine(run_scan())
    except Exception as e:
        st.error(f"Scan Error: {e}")
        return pd.DataFrame()

# Streamlit UI
st.set_page_config(page_title="Shortable Stock Scanner", layout="wide")
st.title('📊 Shortable Stock Scanner (< 20K Shares)')

st.markdown("""
**Purpose:** Find stocks with low shortable shares availability (< 20,000 shares).

**Requirements:**
""")

    st.sidebar.header('⚙️ Parameters')
    st.sidebar.write("**Source for symbols:**")

    # Try to load from us_stock_symbols.csv first
    us_symbols_path = os.path.join(os.path.dirname(__file__), 'us_stock_symbols.csv')
    local_symbols_path = os.path.join(os.path.dirname(__file__), 'symbols.xlsx')
    
    tickers = []
    
    # Priority 1: us_stock_symbols.csv
    if os.path.exists(us_symbols_path):
        try:
            df_symbols = pd.read_csv(us_symbols_path)
            tickers = df_symbols['symbol'].astype(str).str.strip().dropna().unique().tolist()
            st.sidebar.write(f'✓ Loaded {len(tickers)} symbols from us_stock_symbols.csv')
        except Exception as e:
            st.sidebar.warning(f'Failed to load us_stock_symbols.csv: {e}')
    
    # Priority 2: symbols.xlsx
    if not tickers and os.path.exists(local_symbols_path):
        try:
            df_symbols = pd.read_excel(local_symbols_path)
            cols = [c.lower() for c in df_symbols.columns]
            symbol_col = None
            for candidate in ('symbol', 'ticker'):
                if candidate in cols:
                    symbol_col = df_symbols.columns[cols.index(candidate)]
                    break
            if symbol_col is None:
                symbol_col = df_symbols.columns[0]

            tickers = df_symbols[symbol_col].astype(str).str.strip().dropna().unique().tolist()
            st.sidebar.write(f'✓ Loaded {len(tickers)} symbols from symbols.xlsx')
        except Exception as e:
            st.sidebar.warning(f'Failed to load symbols.xlsx: {e}')
    
    # Priority 3: Finnhub
    if not tickers:
        tickers = fetch_symbols_from_finnhub()
        st.sidebar.write(f'✓ Loaded {len(tickers)} symbols from Finnhub')

    st.sidebar.write(f"Total stocks to scan: {len(tickers)}")

# Automatically load data on page load
st.info(f"Loading shortable share data for {len(tickers)} popular stocks...")
df = scan_shortable(tickers)

if not df.empty:
    st.success(f"✅ Found {len(df)} stocks with shortable shares < 20,000")
    
    # Display results sorted by shortable shares (ascending)
    display_df = df[['Ticker', 'Shortable Shares']].copy()
    display_df = display_df.sort_values('Shortable Shares', ascending=True)
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    # Download CSV
    csv = display_df.to_csv(index=False)
    st.download_button(
        label="📥 Download as CSV",
        data=csv,
        file_name=f"shortable_stocks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )
else:
    st.warning("❌ No stocks found with shortable shares < 20,000.")


st.markdown("---")
st.caption("""
**Notes:**
""")
