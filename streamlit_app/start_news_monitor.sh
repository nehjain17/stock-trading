#!/bin/bash
# Start News Monitor in background

cd "$(dirname "$0")"

echo "🚀 Starting News Monitor..."

# Check if already running
if pgrep -f "news_monitor.py" > /dev/null; then
    echo "⚠️  News monitor is already running!"
    echo "   PID: $(pgrep -f 'news_monitor.py')"
    echo ""
    echo "To stop: pkill -f news_monitor"
    echo "To view log: tail -f logs/news_monitor.log"
    exit 1
fi

# Create logs directory
mkdir -p logs

# Start in background
nohup python3 -u news_monitor.py > logs/news_monitor.log 2>&1 &

sleep 2

if pgrep -f "news_monitor.py" > /dev/null; then
    echo "✓ News monitor started successfully!"
    echo "  PID: $(pgrep -f 'news_monitor.py')"
    echo "  Log: logs/news_monitor.log"
    echo ""
    echo "Monitor with: tail -f logs/news_monitor.log"
    echo "Stop with: pkill -f news_monitor"
else
    echo "❌ Failed to start news monitor"
    echo "Check logs/news_monitor.log for errors"
    exit 1
fi
