# Stock Scanner & Data Collection System

A comprehensive stock data collection and scanning system using **Interactive Brokers (IBKR)**, **Yahoo Finance**, **Finnhub**, **Alpha Vantage**, and **Benzinga** APIs.

## Features

- ✅ **Complete US Stock Universe**: 10,153 stocks from NASDAQ, NYSE, AMEX
- ✅ **Yahoo Finance Data**: Shares outstanding, float shares, market cap
- ✅ **IBKR Shortable Shares**: Real-time short availability data
- ✅ **Streamlit Scanner**: Real-time data with multi-source news aggregation
- ✅ **Smart Filtering**: Relative volume, float size, short interest
- ✅ **Intraday Charts**: 5-minute candlestick charts with Plotly
- ✅ **Sequential Fetch**: Rate-limit friendly with 100% success rate
- ✅ **Read-Only Mode**: Safe, no trading/order risk

## Requirements

### System Requirements
- Interactive Brokers TWS (Trader Workstation) or Gateway running
- Python 3.8+
- macOS/Linux/Windows

### API Keys (All Free or Optional)
1. **Finnhub** (Free): https://finnhub.io/register
2. **Alpha Vantage** (Free): https://www.alphavantage.co/api
3. **Benzinga** (Optional): https://www.benzinga.com/apis

## Setup

### 1. Install Dependencies

```bash
cd streamlit_app
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
# Copy the example file
cp .env.example .env

# Edit .env with your API keys
# IBKR_HOST=127.0.0.1
# IBKR_PORT=7497 (paper) or 7496 (live)
# FINNHUB_API_KEY=your_key
# ALPHA_VANTAGE_KEY=your_key
# BENZINGA_API_KEY=your_key (optional)
```

Note: The `.env` file has been populated with the provided API keys. The application
loads keys from `.env` via `python-dotenv`—ensure `.env` remains git-ignored and
do not commit it to version control. If you want to override or rotate keys, edit
the `.env` file in the project root.
### 3. Enable IBKR Read-Only API

1. Open **Interactive Brokers TWS** or **Gateway**
2. Go to **Edit → Global Configuration → API → Settings**
3. ✅ Check "**Read-Only API**"
4. Ensure the port matches your config (7497 for paper, 7496 for live)

### 4. Run the App

```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`

## Data Collection Scripts

### 1. Yahoo Finance Data Collection

**Script**: `sequential_fetch.py`

Fetches fundamental data (shares outstanding, float shares, market cap) for all US stocks using Yahoo Finance API.

**Features**:
- Sequential fetch with 0.5s delays (rate-limit friendly)
- 99%+ success rate
- Auto-saves progress every 100 stocks
- Resumes from last position on restart

**Usage**:
```bash
# Start fresh fetch
python3 sequential_fetch.py

# Run in background
nohup python3 -u sequential_fetch.py > sequential_fetch.log 2>&1 &

# Monitor progress
tail -f sequential_fetch.log

# Check if running
ps aux | grep sequential_fetch
```

**Output**: `all_stocks_complete.csv` (currently 11,000+ stocks)

### 2. IBKR Shortable Shares Collection

**Script**: `fetch_ibkr_shortable_sync.py`

Fetches shortable shares data from Interactive Brokers for all US stocks.

**Requirements**:
- TWS/IB Gateway running with API enabled
- Market hours (9:30 AM - 4:00 PM ET) for best results
- Level 1 market data subscription

**Features**:
- Sequential fetch (~2 seconds per stock)
- Uses generic tick 236 for shortable shares
- Auto-saves progress every 100 stocks
- -1 indicates data not available

**Usage**:
```bash
# Ensure TWS is running first
# Check connection
python3 -c "from ib_insync import IB; ib = IB(); ib.connect('127.0.0.1', 7497, clientId=1); print('Connected!'); ib.disconnect()"

# Start fetch
nohup python3 -u fetch_ibkr_shortable_sync.py > ibkr_fetch.log 2>&1 &

# Monitor progress
tail -f ibkr_fetch.log
```

**Output**: `shortable_data.csv`

**Note**: After-hours availability is limited. For best results, run during market hours.

### 3. IBKR FTP Bulk Download (Alternative)

**Script**: `fetch_ibkr_ftp.py`

Downloads daily shortable shares file from IBKR's FTP server.

**Usage**:
```bash
python3 fetch_ibkr_ftp.py
```

**Output**: `shortable_data_ftp.csv`

**Pros**: Fast, bulk download  
**Cons**: Updated once daily, may not include all stocks

## Scanner Usage

### Main Scanner (`app.py`)

```bash
streamlit run app.py
```

1. **Enter Tickers**: Comma-separated list (e.g., `AAPL,TSLA,AMC,GME`)
2. **Adjust Filters**:
   - **Relative Volume Threshold**: Minimum volume compared to 20-day average
   - **Max Float**: Maximum float size to filter large caps
   - **Min Short %**: Minimum short interest percentage
3. **Click "Scan"**: Fetches real-time data from IBKR and aggregates news
4. **View Results**: 
   - Table of matching stocks
   - Intraday 5-minute chart
   - Aggregated news and catalysts

### Shortable Scanner (`shortable_scanner.py`)

Enhanced scanner with shortable shares data.

```bash
streamlit run shortable_scanner.py
```

**Features**:
- Uses `us_stock_symbols.csv` as primary source (10,153 stocks)
- Displays shortable shares when available
- Fallback to original symbol sources

## Data Files

### Core Data Files

1. **us_stock_symbols.csv** (47KB, 10,153 stocks)
   - Master list of all US stocks from NASDAQ, NYSE, AMEX
   - Source: Official NASDAQ FTP (ftp.nasdaqtrader.com)
   - Single column: `symbol`
   - Excludes OTC, test symbols, and non-standard securities

2. **all_stocks_complete.csv** (822KB, 11,000+ stocks)
   - Yahoo Finance fundamental data
   - Columns: `symbol, name, country, exchange, currency, ipo, share_outstanding, float_shares, market_cap`
   - Updated continuously by `sequential_fetch.py`
   - ~99% success rate

3. **shortable_data.csv** (when generated)
   - IBKR shortable shares data
   - Columns: `symbol, shortable_shares`
   - -1 = data not available
   - Best collected during market hours

## Data Sources

| Source | Data | Rate Limits | Notes |
|--------|------|-------------|-------|
| **Yahoo Finance** | Shares outstanding, float, market cap | Sequential with 0.5s delay | Free, 99% success rate |
| **IBKR** | Price, Volume, Short Interest, Shortable Shares | 100 concurrent lines (default) | Requires TWS/Gateway; market hours best |
| **Finnhub** | Company News, Company Info | 60 req/min (free) | Free tier available |
| **Alpha Vantage** | News Sentiment | 5 req/min (free) | Free tier available |
| **Benzinga** | Premium News | Plan-dependent | Optional; requires API key |
| **NASDAQ FTP** | Official symbol lists | No limit | Daily updates |

## Completed Work

✅ **Symbol Collection**: 10,153 US stocks from NASDAQ/NYSE/AMEX  
✅ **Yahoo Finance Fetch**: 11,000+ stocks with fundamental data (99% success)  
✅ **Sequential Rate-Limit Solution**: 0.5s delays avoid all rate limits  
✅ **IBKR Integration**: Shortable shares via tick type 236  
✅ **Auto-Save Progress**: Every 100 stocks, resume-friendly  
✅ **Clean Project Structure**: Organized archive, logs, output folders  

## Pending Work

⏳ **IBKR Shortable Shares**: Complete fetch during Monday market hours  
⏳ **Data Merge**: Combine Yahoo Finance + IBKR shortable shares  
⏳ **Scanner Enhancement**: Integrate complete dataset into scanner UI  

## Important Notes

⚠️ **Float Data**: Float shares from Yahoo Finance represent public float (shareOutstanding - closely held shares)

⚠️ **Read-Only Mode**: This app ONLY reads data. No trading, no orders, no risk

⚠️ **IBKR Shortable Shares**: 
- Best during market hours (9:30 AM - 4:00 PM ET)
- After-hours data limited to ~200-300 stocks (cached values)
- Requires TWS/IB Gateway running with API enabled
- Uses generic tick type 236 (tick ID 89)

⚠️ **Yahoo Finance Rate Limits**: 
- Parallel requests get blocked ("Invalid Crumb" error)
- Sequential with 0.5s delays = 100% success
- No official rate limit, but enforced server-side

⚠️ **API Rate Limits**: 
- Finnhub: 60 req/min (free), 300 req/min (pro)
- Alpha Vantage: 5 req/min (free)
- Benzinga: Plan-dependent
- IBKR: 100 concurrent market data lines (default)

⚠️ **Real-Time Delays**: Without an active market data subscription in IBKR, data is delayed by 15-20 minutes

## Troubleshooting

### Yahoo Finance Fetch

**"Invalid Crumb" or empty responses**
- Using parallel requests (rate limited)
- Solution: Use `sequential_fetch.py` with 0.5s delays

**Fetch stopped/crashed**
- Check log: `tail sequential_fetch.log`
- Progress auto-saved every 100 stocks
- Resume: Just restart script, it skips completed symbols

**Missing data for some symbols**
- Some symbols may not exist on Yahoo Finance
- Delisted or invalid tickers return errors
- Check `all_stocks_complete.csv` for success rate

### IBKR Connection Issues

### "IBKR Connection Error"
- Ensure TWS/Gateway is running
- Check IBKR_HOST and IBKR_PORT in `.env`
- Verify port: 7497 (paper) or 7496 (live)
- Confirm API access is enabled in TWS

**"No shortable shares data" (all -1 or NaN)**
- Markets are closed → Most stocks return no data
- Solution: Run during market hours (9:30 AM - 4:00 PM ET)
- TWS cache exhausted → Restart TWS/Gateway
- Check connection: `python3 -c "from ib_insync import IB; ib = IB(); ib.connect('127.0.0.1', 7497, clientId=1); print('✓ Connected'); ib.disconnect()"`

**"Data stopped after ~200-300 stocks"**
- After-hours limitation
- TWS market data line limit reached
- Solution: Wait for market hours or restart TWS

### Scanner Issues

### "No data returned"
- Ticker may not be valid or available on IBKR
- Check if market hours (9:30 AM - 4:00 PM ET)
- Verify API keys are correct

### "Rate limit error"
- Wait a few minutes before scanning again
- Reduce number of tickers per scan
- Check free tier limits on APIs

## Project Structure

```
streamlit_app/
├── app.py                          # Main Streamlit scanner UI
├── shortable_scanner.py            # Enhanced scanner with shortable shares
├── sequential_fetch.py             # Yahoo Finance data fetcher (rate-limit safe)
├── fetch_ibkr_shortable_sync.py    # IBKR shortable shares fetcher
├── fetch_ibkr_ftp.py               # IBKR FTP bulk data downloader
├── fetch_symbols.py                # Original symbol list fetcher
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variables template
├── .env                            # Your actual keys (git-ignored)
│
├── us_stock_symbols.csv            # Master list: 10,153 US stocks (NASDAQ/NYSE/AMEX)
├── all_stocks_complete.csv         # Yahoo Finance data (shares, float, market cap)
├── sequential_fetch.log            # Active fetch log
│
├── archive/                        # Old scripts and intermediate files
├── logs/                           # Old log files
├── output_data/                    # Final outputs
└── __pycache__/                    # Python cache
```

## Running Multiple Processes

You can run data collection and scanners simultaneously:

**Terminal 1 - Yahoo Finance Fetch** (if not complete):
```bash
cd streamlit_app
nohup python3 -u sequential_fetch.py > sequential_fetch.log 2>&1 &
tail -f sequential_fetch.log
```

**Terminal 2 - IBKR Shortable Shares** (during market hours):
```bash
cd streamlit_app
# Check TWS is running first
nohup python3 -u fetch_ibkr_shortable_sync.py > ibkr_fetch.log 2>&1 &
tail -f ibkr_fetch.log
```

**Terminal 3 - Streamlit Scanner**:
```bash
cd streamlit_app
streamlit run shortable_scanner.py
```

**Monitor All**:
```bash
# Check running processes
ps aux | grep -E "(sequential_fetch|fetch_ibkr|streamlit)"

# View logs
tail -f sequential_fetch.log
tail -f ibkr_fetch.log
```

## Quick Reference

### Check Process Status
```bash
# Yahoo Finance fetch
ps aux | grep sequential_fetch | grep -v grep
tail -5 sequential_fetch.log

# IBKR fetch  
ps aux | grep fetch_ibkr | grep -v grep
tail -5 ibkr_fetch.log

# Count completed stocks
wc -l all_stocks_complete.csv
grep -v ",-1$" shortable_data.csv | wc -l  # Count with data
```

### Stop Processes
```bash
# Stop Yahoo Finance fetch
pkill -9 -f sequential_fetch

# Stop IBKR fetch
pkill -9 -f fetch_ibkr_shortable_sync
```

### Data Verification
```bash
# Check for specific symbols
grep "AAPL\|TSLA\|GME" all_stocks_complete.csv
grep "AAPL\|TSLA\|GME" shortable_data.csv

# Success rate
tail -1 sequential_fetch.log
```

## Future Enhancements

- [x] Complete US stock universe collection (10,153 stocks)
- [x] Yahoo Finance fundamental data fetch
- [x] Sequential rate-limit solution
- [x] IBKR shortable shares integration
- [ ] Merge Yahoo + IBKR data into master CSV
- [ ] Database integration to store scan results
- [ ] Scheduled daily updates (cron jobs)
- [ ] Email alerts on catalyst news
- [ ] Backtest scanner logic with historical data
- [ ] Advanced charting with moving averages, indicators
- [ ] Portfolio tracking and position management
- [ ] Web scraping for additional float data sources

## License

MIT
