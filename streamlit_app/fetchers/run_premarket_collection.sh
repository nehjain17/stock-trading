#!/bin/bash
# Run this Monday morning at 4:00 AM ET to collect premarket IBKR data

cd "$(dirname "$0")"

echo "========================================================================"
echo "PREMARKET DATA COLLECTION - $(date)"
echo "========================================================================"
echo ""

# Make sure TWS/Gateway is running
echo "Checking if IBKR TWS/Gateway is running..."
if ! pgrep -f "tws|gateway" > /dev/null; then
    echo "⚠️  WARNING: TWS/Gateway not detected!"
    echo "   Please start TWS or IB Gateway before running this script"
    exit 1
fi
echo "✓ TWS/Gateway is running"
echo ""

# Collect IBKR premarket data for all exchange-traded low float stocks
echo "Collecting IBKR premarket data..."
python3 fetch_data_ibkr.py --input ../input/low_float_stocks_100M_exchange_only.csv

echo ""
echo "========================================================================"
echo "✓ Premarket data collection complete!"
echo "  Check: ../output/ibkr_market_data.csv"
echo "  Launch dashboard: cd .. && python3 -m streamlit run dashboard.py"
echo "========================================================================"
