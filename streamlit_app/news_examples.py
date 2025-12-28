"""
Example: Using Pull + Push News System in Scanner

Shows how to combine:
1. Push: Background monitor continuously caching news
2. Pull: Scanner queries cache for instant results
3. Fallback: Real-time API if cache miss
"""

from news_api import (
    get_news_for_symbols,
    get_catalyst_stocks,
    get_breaking_news,
    get_most_active_symbols
)
import requests
import os
from dotenv import load_dotenv

load_dotenv()

def get_news_hybrid(symbols, hours=24):
    """
    Hybrid approach: Try cache first, fallback to API
    
    Args:
        symbols: List of stock symbols to get news for
        hours: Look back period
    
    Returns:
        Dict mapping symbol -> news items
    """
    # Step 1: Try cache (FAST - instant results)
    cached_news = get_news_for_symbols(symbols, hours=hours)
    
    # Step 2: Identify symbols with no/little cached news
    symbols_needing_fetch = []
    for symbol in symbols:
        if len(cached_news.get(symbol, [])) < 3:  # Less than 3 items cached
            symbols_needing_fetch.append(symbol)
    
    # Step 3: Fetch missing symbols from API (SLOW - real-time)
    if symbols_needing_fetch:
        print(f"Fetching real-time news for {len(symbols_needing_fetch)} symbols...")
        fresh_news = fetch_from_api_realtime(symbols_needing_fetch, hours)
        
        # Merge with cached results
        for symbol, news_items in fresh_news.items():
            if symbol not in cached_news:
                cached_news[symbol] = []
            cached_news[symbol].extend(news_items)
    
    return cached_news

def fetch_from_api_realtime(symbols, hours=24):
    """Fallback: Fetch directly from API for uncached symbols"""
    # Use existing Benzinga/Finnhub fetch logic from app.py
    # This is your existing code
    from datetime import datetime, timedelta
    
    news_by_symbol = {symbol: [] for symbol in symbols}
    
    # Example: Finnhub
    FINNHUB_KEY = os.getenv('FINNHUB_API_KEY')
    if FINNHUB_KEY:
        since = datetime.now() - timedelta(hours=hours)
        for symbol in symbols:
            try:
                url = 'https://finnhub.io/api/v1/company-news'
                params = {
                    'symbol': symbol,
                    'from': since.strftime('%Y-%m-%d'),
                    'to': datetime.now().strftime('%Y-%m-%d'),
                    'token': FINNHUB_KEY
                }
                response = requests.get(url, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    news_by_symbol[symbol] = [
                        {
                            'headline': item.get('headline'),
                            'summary': item.get('summary', '')[:500],
                            'source': 'Finnhub',
                            'url': item.get('url'),
                            'published_at': datetime.fromtimestamp(item.get('datetime', 0)).isoformat(),
                            'sentiment': None,
                            'is_catalyst': False
                        }
                        for item in data[:10]
                    ]
            except Exception as e:
                print(f"Error fetching {symbol}: {e}")
    
    return news_by_symbol

# ============================================
# Example 1: Scanner with hybrid news
# ============================================

def scan_with_news(tickers):
    """Main scanner function with hybrid news approach"""
    symbols = [t.strip().upper() for t in tickers.split(',')]
    
    print(f"\n📊 Scanning {len(symbols)} stocks...")
    
    # Get news using hybrid approach
    news_data = get_news_hybrid(symbols, hours=24)
    
    for symbol in symbols:
        news_items = news_data.get(symbol, [])
        catalyst_items = [n for n in news_items if n.get('is_catalyst')]
        
        print(f"\n{symbol}:")
        print(f"  📰 Total news: {len(news_items)}")
        print(f"  🎯 Catalysts: {len(catalyst_items)}")
        
        if catalyst_items:
            print(f"  Latest catalyst: {catalyst_items[0]['headline'][:60]}...")

# ============================================
# Example 2: Catalyst scanner
# ============================================

def scan_catalysts():
    """Find stocks with recent catalysts from cache"""
    print("\n🎯 Scanning for catalyst stocks...")
    
    # This is INSTANT - queries local database
    catalyst_stocks = get_catalyst_stocks(hours=24, min_news=2)
    
    print(f"\nFound {len(catalyst_stocks)} stocks with multiple catalysts:\n")
    
    for stock in catalyst_stocks[:10]:
        print(f"{stock['symbol']:6} - {stock['catalyst_count']} catalysts")
        for headline in stock['headlines'][:2]:
            print(f"  • {headline[:70]}")
        print()

# ============================================
# Example 3: Breaking news alert
# ============================================

def check_breaking_news():
    """Check for breaking news in last 30 minutes"""
    breaking = get_breaking_news(minutes=30)
    
    if breaking:
        print(f"\n⚡ {len(breaking)} breaking news items!\n")
        for item in breaking[:5]:
            print(f"{item['symbol']:6} - {item['headline'][:60]}")
    else:
        print("\n✓ No breaking news in last 30 minutes")

# ============================================
# Example 4: Most active stocks by news
# ============================================

def find_most_active():
    """Find stocks with most news activity"""
    active = get_most_active_symbols(hours=24, limit=20)
    
    print("\n📈 Most active stocks (by news volume):\n")
    for stock in active:
        catalyst_pct = (stock['catalyst_count'] / stock['news_count'] * 100) if stock['news_count'] > 0 else 0
        print(f"{stock['symbol']:6} - {stock['news_count']:3} news ({stock['catalyst_count']} catalysts, {catalyst_pct:.0f}%)")


if __name__ == '__main__':
    print("=" * 60)
    print("News System Examples (Pull + Push)")
    print("=" * 60)
    
    # Example 1: Hybrid news for specific stocks
    print("\n1. Hybrid News Fetch:")
    scan_with_news("AAPL,TSLA,NVDA")
    
    # Example 2: Find catalyst stocks
    print("\n" + "=" * 60)
    print("2. Catalyst Scanner:")
    scan_catalysts()
    
    # Example 3: Breaking news
    print("\n" + "=" * 60)
    print("3. Breaking News:")
    check_breaking_news()
    
    # Example 4: Most active
    print("\n" + "=" * 60)
    print("4. Most Active Stocks:")
    find_most_active()
