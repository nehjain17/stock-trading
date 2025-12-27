# Stock Scanner App - Streamlit

This is a real-time stock discovery application using **Interactive Brokers (IBKR)**, **Finnhub**, **Alpha Vantage**, and **Benzinga** APIs.

## Features

- ✅ **Real-time Data from IBKR**: Price, volume, short interest, shortable shares
- ✅ **Multi-Source News Aggregation**: IBKR, Finnhub, Alpha Vantage, Benzinga
- ✅ **Smart Filtering**: Relative volume, float size, short interest
- ✅ **Intraday Charts**: 5-minute candlestick charts with Plotly
- ✅ **Catalyst Detection**: Automatically finds news with bullish keywords
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

## Usage

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

## Data Sources

| Source | Data | Notes |
|--------|------|-------|
| **IBKR** | Price, Volume, Short Interest, Shortable Shares | Real-time; requires active subscription |
| **Finnhub** | Company News, Company Info | Free tier available |
| **Alpha Vantage** | News Sentiment | Free tier available |
| **Benzinga** | Premium News | Optional; requires API key |

## Important Notes

⚠️ **Float Approximation**: The "Float Approx" is calculated from shareOutstanding (fundamental data). For true float (public outstanding shares), upgrade IBKR subscriptions.

⚠️ **Read-Only Mode**: This app ONLY reads data. No trading, no orders, no risk.

⚠️ **API Rate Limits**: 
- Finnhub: 60 req/min (free), 300 req/min (pro)
- Alpha Vantage: 5 req/min (free)
- Benzinga: Depends on plan
- IBKR: No hard limits; depends on market data subscriptions

⚠️ **Real-Time Delays**: Without an active market data subscription in IBKR, data is delayed by 15-20 minutes.

## Troubleshooting

### "IBKR Connection Error"
- Ensure TWS/Gateway is running
- Check IBKR_HOST and IBKR_PORT in `.env`
- Verify port: 7497 (paper) or 7496 (live)
- Confirm API access is enabled in TWS

### "No data returned"
- Ticker may not be valid or available on IBKR
- Check if market hours (9:30 AM - 4:00 PM ET)
- Verify API keys are correct

### "Rate limit error"
- Wait a few minutes before scanning again
- Reduce number of tickers per scan
- Check free tier limits on APIs

## Architecture

```
streamlit_app/
├── app.py              # Main Streamlit application
├── requirements.txt    # Python dependencies
├── .env.example       # Environment variables template
├── .env               # Your actual keys (git-ignored)
└── .streamlit/
    └── config.toml    # Streamlit configuration
```

## Running with Other Services

You can run all three services simultaneously:

**Terminal 1 - FastAPI Backend**:
```bash
cd backend
source venv/bin/activate
python app/main.py
```

**Terminal 2 - React Frontend**:
```bash
cd frontend
npm run dev
```

**Terminal 3 - Streamlit App**:
```bash
cd streamlit_app
streamlit run app.py
```

Then access:
- Streamlit: `http://localhost:8501`
- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`

## Future Enhancements

- [ ] Database integration to store scan results
- [ ] Backtest scanner logic with historical data
- [ ] Email alerts on catalyst news
- [ ] Integration with FastAPI backend for data persistence
- [ ] Advanced charting with moving averages, indicators
- [ ] Portfolio tracking and position management

## License

MIT
