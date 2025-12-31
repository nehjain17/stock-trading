# 📈 Stock Trading System - Clean Architecture

## 🎯 Quick Start

### 1. Test with 10 stocks (recommended first)
```bash
cd fetchers

# Fetch market data from Yahoo (best OTC coverage)
python fetch_data_yahoo.py --limit 10

# Fetch news from Benzinga (bulk API)
python fetch_news_benzinga.py --limit 10

# Launch dashboard (from main folder)
cd ..
streamlit run dashboard.py
```

### 2. Full data collection
```bash
cd fetchers

# Yahoo Finance (unlimited, best for low float stocks)
python fetch_data_yahoo.py

# Benzinga news (60 calls/min, bulk: 50 stocks/call)
python fetch_news_benzinga.py --days 7

# Finnhub news (60 calls/min, individual calls)
python fetch_news_finnhub.py --days 7

# IBKR data (requires TWS/Gateway running on port 7497)
python fetch_data_ibkr.py

# Moomoo data (requires OpenD running, US permissions needed)
python fetch_data_moomoo.py

# Or use custom input file
python fetch_data_yahoo.py --input ../input/all_stocks_complete.csv --limit 100
```

## 📁 File Structure

### ✅ **Main Files** (use these)
```
dashboard.py                → Main UI (run from root)

fetchers/                   → All data fetchers
  ├── fetch_data_ibkr.py    → IBKR market data
  ├── fetch_data_moomoo.py  → Moomoo market data
  ├── fetch_data_yahoo.py   → Yahoo Finance data
  ├── fetch_news_benzinga.py → Benzinga news (bulk API)
  └── fetch_news_finnhub.py → Finnhub news

input/                      → Source data files
  ├── low_float_stocks_10M.csv    → Stocks < $10M market cap
  ├── low_float_stocks_50M.csv    → Stocks < $50M market cap
  ├── low_float_stocks_100M.csv   → Stocks < $100M (4,365 stocks)
  ├── low_float_stocks_500M.csv   → Stocks < $500M market cap
  └── all_stocks_complete.csv     → All US stocks (11,799 stocks)

output/                     → All generated data
  ├── ibkr_market_data.csv
  ├── moomoo_market_data.csv
  ├── yahoo_market_data.csv
  ├── benzinga_news.csv
  └── finnhub_news.csv
```

### 🗑️ **Old Files** (can be archived)
```
archive/
  ├── fetch_ibkr_low_float.py      → Old IBKR script
  ├── realtime_stock_data.py       → Old multi-source script
  ├── fetch_all_benzinga_news.py   → Old Benzinga script
  ├── news_monitor.py              → Old monitoring script
  ├── fetch_low_float_news.py      → Old news script
  └── ... (other old files)
```

## 🎨 Data Sources

### Market Data
| Source | Speed | Coverage | OTC Support | Best For |
|--------|-------|----------|-------------|----------|
| **Yahoo Finance** | Fast | Excellent | ✅ Yes | Low float/OTC stocks |
| **IBKR** | Medium | Good | ❌ No | Exchange-traded stocks |
| **Moomoo** | Fast | Good | ❌ No | Real-time quotes (requires permissions) |

### News Data
| Source | Speed | API Type | Best For |
|--------|-------|----------|----------|
| **Benzinga** | Fast | Bulk (50 stocks/call) | Large watchlists |
| **Finnhub** | Slow | Individual calls | Detailed company news |

## 📊 Dashboard Features

- **Top Candidates**: Short squeeze potential scoring
- **Latest News**: Combined news from all sources
- **All Stocks**: Full data table with download
- **Filters**: Volume, squeeze score, news-only

## 🔄 Workflow
cd fetchers
   python fetch_data_yahoo.py
   python fetch_news_benzinga.py
   ```

2. **View Dashboard**
   ```bash
   cd ..

2. **View Dashboard**
   ```bash
   streamlit run dashboard.py
   ```

3. **Refresh** (click "🔄 Refresh Data" button in dashboard)

## 📝 Command Line Options

All fetchers support:
- `--input <file>`: Source CSV file (default: low_float_stocks_100M.csv)
- `--limit <number>`: Limit number of stocks to process
- `--days <number>`: Days back for news (default: 7)

## ⚙️ Prerequisites

### Required
- Python 3.9+
- API Keys in `.env`:
  ```
  BENZINGA_API_KEY=your_key
  FINNHUB_API_KEY=your_key
  ```

### Optional
- **IBKR**: TWS or Gateway running on port 7497
- **Moomoo**: OpenD running on port 11111 with US market permissions

## 🧹 Cleanup

To archive old files:
```bash
python cleanup.py
```

This moves old scripts to `archive/` folder while keeping source data files.

## 💡 Tips

1. **Start Small**: Always test with `--limit 10` first
2. **Yahoo for OTC**: Use Yahoo Finance for pink sheet/OTC stocks
3. **Benzinga for Speed**: Bulk API processes 50 stocks per call
4. **Check Permissions**: Moomoo requires US market permissions enabled
5. **IBKR for Quality**: Best data for exchange-traded stocks

## 🎯 Finding Short Squeeze Candidates

The dashboard calculates squeeze score based on:
- **Volume spike** (30 points): Volume > 2x average
- **High short interest** (30 points): Short % > 20%
- **Low float** (25 points): Float < 10M shares
- **Price action** (15 points): Intraday gain > 10%

**Score > 70** = Strong candidate
**Score 50-70** = Moderate potential
**Score < 50** = Lower probability
