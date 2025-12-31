# Moomoo OpenAPI Setup Guide

## Prerequisites
1. Moomoo account (sign up at moomoo.com)
2. OpenD downloaded and configured
3. Python Moomoo SDK installed

## Installation Steps

### 1. Install Moomoo Python SDK
```bash
pip install moomoo-api
```

### 2. Download OpenD for macOS
1. Visit: https://www.moomoo.com/download/OpenAPI
2. Choose **Visualization OpenD** (GUI version, easier)
3. Download macOS version (e.g., `opend_mac_v9.6.XXXX.tar`)
4. Extract to `~/OpenD`

### 3. Configure OpenD.xml
Edit `~/OpenD/OpenD.xml`:
```xml
<config>
    <ip>127.0.0.1</ip>
    <api_port>11111</api_port>
    <login_account>your_moomoo_email</login_account>
    <login_pwd>MD5_PASSWORD_HERE</login_pwd>
    <lang>en</lang>
    <log_level>info</log_level>
</config>
```

**Generate MD5 password:**
```bash
python3 -c "import hashlib; print(hashlib.md5(b'YOUR_PASSWORD').hexdigest())"
```

### 4. Fix macOS Security Issues
```bash
cd ~/OpenD
./fixrun.sh  # If provided
# OR
xattr -d com.apple.quarantine OpenD.app
```

### 5. Start OpenD

**Command Line:**
```bash
cd ~/OpenD
./OpenD.app/Contents/MacOS/OpenD -console -cfg_file=$PWD/OpenD.xml
```

**GUI (Easier):**
```bash
open ~/OpenD/OpenD.app
# Log in via the GUI window
```

### 6. Verify Connection
```bash
# Check if OpenD is running
ps aux | grep OpenD

# Check if port is listening
lsof -i:11111

# Test connection
telnet 127.0.0.1 11111
```

## Running the Scripts

### Scan All Low Float Stocks
```bash
cd /Users/shaurya/Documents/stock-trading/streamlit_app
python3 moomoo_fetcher.py
```

**Output:**
- `moomoo_scan_results.csv` - Complete scan results
- Console shows top squeeze candidates

### Real-time Monitor (Live Alerts)
```bash
python3 moomoo_realtime_monitor.py
```

**Features:**
- Monitors top 50 low float stocks in real-time
- Alerts on volume spikes (>3x average)
- Alerts on price breakouts (>10%)
- Updates every 5 seconds

## Data Available from Moomoo

| Data Type | Available | Notes |
|-----------|-----------|-------|
| Real-time quotes | ✅ Yes | Price, volume, change |
| Average volume | ✅ Yes | 3-month average |
| Market cap | ✅ Yes | Total valuation |
| Float shares | ✅ Yes | Shares available for trading |
| Shares outstanding | ✅ Yes | Total shares issued |
| Short interest | ⚠️ Limited | May require premium |
| Historical data | ✅ Yes | K-line (candlestick) data |
| Level 2 quotes | ✅ Yes | Order book depth |

## Subscription Limits

**Free Tier:**
- Max 50 stock subscriptions
- Real-time US quotes
- Basic fundamentals

**Premium:**
- More subscriptions
- Extended data access

## Common Issues

### "Connection refused"
- OpenD not running → Start OpenD
- Wrong port → Check OpenD.xml (should be 11111)

### "Login failed"
- Wrong MD5 password → Regenerate MD5
- 2FA required → Enter code in OpenD console/GUI

### "No data returned"
- Invalid symbol format → Use `US.SYMBOL` format
- Market closed → Data available during US market hours

### "Rate limit exceeded"
- Too many requests → Add delays between calls
- Reduce watchlist size

## Integration with Your System

### Option 1: Periodic Scan
Run `moomoo_fetcher.py` via cron every 30 minutes:
```cron
*/30 9-16 * * 1-5 cd /Users/shaurya/Documents/stock-trading/streamlit_app && python3 moomoo_fetcher.py
```

### Option 2: Real-time Monitor
Keep `moomoo_realtime_monitor.py` running during market hours:
```bash
nohup python3 moomoo_realtime_monitor.py > logs/moomoo_monitor.log 2>&1 &
```

### Option 3: Combine with News
Integrate Moomoo data with your news alerts:
1. Moomoo detects volume spike
2. Check your news database for catalysts
3. Alert if both conditions met

## Logs & Debugging

**OpenD logs:**
```bash
tail -f ~/.com.moomoo.OpenD/Log/opend.log
```

**Python script logs:**
```bash
# Add to cron or script
python3 moomoo_fetcher.py 2>&1 | tee logs/moomoo.log
```

## Resources

- Official docs: https://openapi.moomoo.com/moomoo-api-doc/en/
- Python SDK: https://github.com/moomoo-inc/py-moomoo-api
- Community: https://www.moomoo.com/community

## Next Steps

1. ✅ Install SDK: `pip install moomoo-api`
2. ✅ Download & configure OpenD
3. ✅ Start OpenD
4. ✅ Run test: `python3 moomoo_fetcher.py`
5. 🔄 Integrate with news alerts
6. 🔄 Build dashboard combining all data sources
