import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import asyncio

# Ensure an asyncio event loop exists for Streamlit's script thread.
# Streamlit runs user code in a worker thread without a running loop,
# but libraries like `ib_insync` expect `asyncio.get_event_loop()` to
# return a loop at import-time. Create and set one if missing.
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
        # If loop is already running (Streamlit), schedule the coroutine
        # and wait for its result in a thread-safe way.
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()
    else:
        return loop.run_until_complete(coro)
import time
from ib_insync import IB, Stock, BarData
from finnhub import Client as FinnhubClient
import requests  # For Alpha Vantage, Benzinga
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Keys - Load from .env file
FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY', 'your_finnhub_key')
ALPHA_VANTAGE_KEY = os.getenv('ALPHA_VANTAGE_KEY', 'your_alpha_vantage_key')
BENZINGA_API_KEY = os.getenv('BENZINGA_API_KEY', '')
IBKR_HOST = os.getenv('IBKR_HOST', '127.0.0.1')
IBKR_PORT = int(os.getenv('IBKR_PORT', 7497))  # Paper; 7496 for live
IBKR_CLIENT_ID = int(os.getenv('IBKR_CLIENT_ID', 1))

# Clients
try:
    finnhub_client = FinnhubClient(api_key=FINNHUB_API_KEY)
except Exception as e:
    st.error(f"Finnhub Client Error: {e}")

# IBKR Connection (Read-Only: Ensure "Read-Only API" checked in TWS Global Config > API > Settings)
async def connect_ibkr():
    """Connect to Interactive Brokers"""
    try:
        ib = IB()
        # Connect in read-only mode to ensure this client never sends
        # order or account-modifying requests. This flags the session
        # as read-only to TWS/Gateway.
        ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID, readonly=True)
        await asyncio.sleep(0.5)  # Wait for connection
        return ib
    except Exception as e:
        st.error(f"IBKR Connection Error: {e}. Ensure TWS is running with Read-Only API enabled.")
        return None

# IBKR Data Fetch (All in one for efficiency)
async def get_ibkr_data(ib, ticker):
    """Fetch real-time and historical data from IBKR"""
    try:
        contract = Stock(ticker, 'SMART', 'USD')
        
        # Real-time Price/Volume (reqMktData for snapshot)
        ib.reqMarketDataType(4)  # Delayed if no real-time sub
        ib.reqMktData(contract, '', True, False)  # Snapshot
        await asyncio.sleep(1)  # Wait for data
        mkt_data = ib.ticker(contract)
        price = mkt_data.marketPrice()
        today_volume = mkt_data.volume
        
        # Historical for Avg Volume (20 days)
        end = datetime.now()
        bars = await ib.reqHistoricalDataAsync(contract, end, '20 D', '1 day', 'TRADES', 1, 1, False, [])
        avg_volume = sum(bar.volume for bar in bars[:-1]) / (len(bars) - 1) if len(bars) > 1 else 0
        rel_volume = today_volume / avg_volume if avg_volume > 0 else 0
        
        # Float Approx (sharesOutstanding; not true float)
        try:
            fundamentals = await ib.reqFundamentalDataAsync(contract, 'ReportsFinSummary')
            float_approx = fundamentals.find('TotalOutstanding') if fundamentals else 0
        except:
            float_approx = 0
        
        # Short % Approx (from short interest tick if subbed; else use shortable)
        try:
            shortable = await ib.reqShortableSharesAsync(contract)
        except:
            shortable = 0
        short_interest = mkt_data.shortInterest if hasattr(mkt_data, 'shortInterest') else 0
        
        # Intraday Bars for Chart (5-min)
        intraday_bars = await ib.reqHistoricalDataAsync(contract, end, '1 D', '5 mins', 'TRADES', 1, 1, False, [])
        
        # IBKR News
        ibkr_news = []
        try:
            providers = await ib.reqNewsProvidersAsync()
            if providers:
                for provider in providers[:2]:  # Limit to 2 providers for speed
                    try:
                        headlines = await ib.reqNewsHeadlinesAsync(contract, provider.code)
                        ibkr_news.extend([h.headline for h in headlines.headlines[:3]])
                    except:
                        pass
        except:
            pass
        
        return {
            'Ticker': ticker,
            'Price': price,
            'Volume': today_volume,
            'Avg Volume': avg_volume,
            'Rel Volume': rel_volume,
            'Float Approx': float_approx,
            'Short %': short_interest,
            'Shortable Shares': shortable,
            'Intraday Bars': intraday_bars,
            'IBKR News': ', '.join(ibkr_news[:5])  # Top 5
        }
    except Exception as e:
        st.warning(f"Error fetching data for {ticker}: {e}")
        return None

# Multi-News Aggregate (Free APIs + IBKR)
def get_news(ibkr_news, ticker):
    """Aggregate news from multiple sources"""
    news_list = ibkr_news.split(', ') if ibkr_news else []
    
    try:
        # Finnhub
        today = datetime.now().strftime('%Y-%m-%d')
        fh_news = finnhub_client.company_news(ticker, _from=today, to=today)
        news_list.extend([item['headline'] for item in fh_news[:5]])
    except Exception as e:
        st.warning(f"Finnhub news error: {e}")
    
    try:
        # Alpha Vantage
        av_url = f'https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={ticker}&apikey={ALPHA_VANTAGE_KEY}'
        av_resp = requests.get(av_url, timeout=5).json()
        av_feed = av_resp.get('feed', [])
        news_list.extend([item['title'] for item in av_feed[:5]])
    except Exception as e:
        st.warning(f"Alpha Vantage news error: {e}")
    
    try:
        # Benzinga (if key)
        if BENZINGA_API_KEY:
            bz_url = f'https://api.benzinga.com/api/v2/news?token={BENZINGA_API_KEY}&tickers={ticker}'
            bz_resp = requests.get(bz_url, timeout=5)
            if bz_resp.status_code == 200:
                try:
                    bz_data = bz_resp.json()
                    news_list.extend([item['title'] for item in bz_data.get('news', [])[:5]])
                except (ValueError, KeyError):
                    pass  # Skip Benzinga if response is not valid JSON
            else:
                pass  # Skip Benzinga on HTTP error
    except Exception as e:
        pass  # Silently skip Benzinga on timeout or connection error
    
    # Dedupe & Catalyst Filter
    positive_keywords = ['earnings beat', 'acquisition', 'partnership', 'FDA', 'upgrade', 'bullish', 'breakout']
    unique_news = set(news_list)
    catalyst_news = [n for n in unique_news if any(kw.lower() in n.lower() for kw in positive_keywords)]
    return ', '.join(catalyst_news) if catalyst_news else 'No specific catalysts found'

# Scanner
def scan_stocks(tickers, vol_threshold=2.0, float_max=10000000, short_min=20):
    """Scan stocks based on criteria"""
    try:
        async def run_scan():
            ib = await connect_ibkr()
            if not ib:
                return pd.DataFrame()
            
            results = []
            progress_bar = st.progress(0)
            
            for idx, ticker in enumerate(tickers):
                try:
                    data = await get_ibkr_data(ib, ticker)
                    if not data:
                        progress_bar.progress((idx + 1) / len(tickers))
                        continue
                    
                    # Aggregate News
                    data['News'] = get_news(data['IBKR News'], ticker)
                    
                    # Filter (use float approx)
                    if (data['Rel Volume'] > vol_threshold and
                        data['Float Approx'] < float_max and
                        data['Short %'] > short_min and
                        data['Shortable Shares'] > 0):
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
st.set_page_config(page_title="Stock Scanner", layout="wide")
st.title('📊 IBKR Read-Only Stock Scanner')

st.markdown("""
**Requirements:**
- Interactive Brokers TWS/Gateway running with Read-Only API enabled
- API Keys: Finnhub, Alpha Vantage (free), Benzinga (optional)
- See `.env.example` for configuration
""")

st.sidebar.header('⚙️ Parameters')
vol_threshold = st.sidebar.slider('Relative Volume Threshold', 1.0, 5.0, 2.0, 0.1)
float_max = st.sidebar.number_input('Max Float (approx)', value=10000000, step=1000000)
short_min = st.sidebar.number_input('Min Short Interest %', value=20.0, step=5.0)
tickers_input = st.sidebar.text_input('Tickers (comma-separated)', 'AAPL,TSLA,AMC,GME')

tickers = [t.strip().upper() for t in tickers_input.split(',') if t.strip()]

col1, col2 = st.columns([1, 4])
with col1:
    scan_button = st.button('🔍 Scan', use_container_width=True)

if scan_button and tickers:
    st.info(f"Scanning {len(tickers)} tickers...")
    df = scan_stocks(tickers, vol_threshold, float_max, short_min)
    
    if not df.empty:
        st.success(f"✅ Found {len(df)} matches")
        
        # Display results
        display_df = df[['Ticker', 'Price', 'Volume', 'Rel Volume', 'Float Approx', 'Short %', 'Shortable Shares']].copy()
        display_df = display_df.sort_values('Rel Volume', ascending=False)
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        # Chart & News
        st.subheader('📈 Details')
        selected = st.selectbox('Select ticker for chart and news', df['Ticker'].values)
        
        if selected:
            col1, col2 = st.columns([2, 1])
            
            with col1:
                row = df[df['Ticker'] == selected].iloc[0]
                bars = row['Intraday Bars']
                
                if bars and len(bars) > 0:
                    try:
                        fig = go.Figure(data=[go.Candlestick(
                            x=[bar.date for bar in bars],
                            open=[bar.open for bar in bars],
                            high=[bar.high for bar in bars],
                            low=[bar.low for bar in bars],
                            close=[bar.close for bar in bars],
                            name=selected
                        )])
                        fig.update_layout(
                            title=f'{selected} Intraday Chart (5-min)',
                            yaxis_title='Price ($)',
                            xaxis_title='Time',
                            template='plotly_white',
                            height=500
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    except Exception as e:
                        st.error(f"Chart error: {e}")
                else:
                    st.warning("No intraday data available")
            
            with col2:
                st.metric("Price", f"${row['Price']:.2f}")
                st.metric("Rel Volume", f"{row['Rel Volume']:.2f}x")
                st.metric("Short %", f"{row['Short %']:.1f}%")
            
            st.subheader('📰 Aggregated News & Catalysts')
            st.write(row['News'])
    else:
        st.warning("❌ No matches found. Try adjusting filters or ensure IBKR TWS is running with Read-Only API enabled.")
elif scan_button:
    st.warning("⚠️ Please enter at least one ticker")

st.markdown("---")
st.caption("""
**Notes:**
- All data sourced from IBKR (read-only mode). Ensure TWS Global Config > API > Settings has "Read-Only API" enabled.
- Float is approximated from sharesOutstanding. For real-time and accurate data, upgrade IBKR subscriptions.
- News aggregated from IBKR, Finnhub, Alpha Vantage, and Benzinga for comprehensive coverage.
- Relative Volume = Today's Volume / 20-day Average Volume
- Handle API rate limits and timeouts appropriately.
""")
