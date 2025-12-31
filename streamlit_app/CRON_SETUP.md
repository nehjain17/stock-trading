# Cron Job Setup for Low Float News

## Updated Script
`fetch_low_float_news.py` now:
- ✅ Fetches from **Benzinga** (bulk: ~88 batches × 1s = ~2 min)
- ✅ Fetches from **Finnhub** (individual: 4,365 stocks × 1s = ~73 min)
- ✅ Total time: **~75 minutes** for all 4,365 low float stocks
- ✅ Saves to database with catalyst detection
- ✅ No user input required (cron-friendly)

## Quick Setup

### 1. Test the script first:
```bash
cd /Users/shaurya/Documents/stock-trading/streamlit_app
python3 fetch_low_float_news.py
```

### 2. Open crontab editor:
```bash
crontab -e
```

### 3. Add one of these schedules:

**Every 2 hours (recommended):**
```cron
0 */2 * * * /Users/shaurya/Documents/stock-trading/streamlit_app/run_low_float_news.sh
```

**Every hour:**
```cron
0 * * * * /Users/shaurya/Documents/stock-trading/streamlit_app/run_low_float_news.sh
```

**Every 90 minutes (right after script completes):**
```cron
0 */1 * * * /Users/shaurya/Documents/stock-trading/streamlit_app/run_low_float_news.sh
30 */1 * * * /Users/shaurya/Documents/stock-trading/streamlit_app/run_low_float_news.sh
```

**Market hours only (9:30 AM - 4:00 PM ET, every hour):**
```cron
30 9-16 * * 1-5 /Users/shaurya/Documents/stock-trading/streamlit_app/run_low_float_news.sh
```

### 4. Save and exit (in vi/vim: press `ESC`, type `:wq`, press `ENTER`)

### 5. Verify cron job is scheduled:
```bash
crontab -l
```

### 6. Check logs:
```bash
tail -f /Users/shaurya/Documents/stock-trading/streamlit_app/logs/low_float_news.log
```

## Schedule Recommendations

| Frequency | Use Case | News Delay |
|-----------|----------|------------|
| Every 90 min | Best for day trading | Max 90 min old |
| Every 2 hours | Good balance | Max 120 min old |
| Every 3 hours | Resource saving | Max 180 min old |
| Market hours only | Active trading days | Fresh during market hours |

## Manual Run (Test)
```bash
cd /Users/shaurya/Documents/stock-trading/streamlit_app
./run_low_float_news.sh
```

## Stop Cron Job
```bash
crontab -e
# Comment out or delete the line, save and exit
```

## Performance Metrics
- **Benzinga**: ~2 minutes (88 bulk API calls)
- **Finnhub**: ~73 minutes (4,365 individual calls at 60/min)
- **Total**: ~75 minutes per run
- **Database**: SQLite with duplicate prevention

## Notes
- Script uses both Benzinga (fast) and Finnhub (comprehensive)
- Database automatically deduplicates news
- Logs are auto-rotated to keep last 1000 lines
- API keys read from `.env` file
