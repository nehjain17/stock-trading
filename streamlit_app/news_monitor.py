#!/usr/bin/env python3
"""
Background News Monitor - Continuously fetches and caches news
Push approach: Polls APIs every N minutes and pushes to database
"""
import os
import time
import sqlite3
import pandas as pd
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import json

load_dotenv()

# Configuration
BENZINGA_API_KEY = os.getenv('BENZINGA_API_KEY')
FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY')
ALPHA_VANTAGE_KEY = os.getenv('ALPHA_VANTAGE_KEY')

# Monitoring settings
POLL_INTERVAL = 300  # 5 minutes
WATCHLIST_SIZE = 11800  # Top N stocks to monitor (set to 11800 for all stocks)
BATCH_SIZE = 50  # Fetch N stocks per batch
DB_PATH = 'news_cache.db'

# Keywords for catalyst detection
CATALYST_KEYWORDS = [
    'acquisition', 'merger', 'fda approval', 'earnings beat',
    'breakthrough', 'contract', 'partnership', 'collaboration',
    'clinical trial', 'phase 2', 'phase 3', 'approved',
    'revenue growth', 'guidance raised', 'buyout', 'tender offer'
]

def init_database():
    """Initialize SQLite database for news cache"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # News table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            headline TEXT NOT NULL,
            summary TEXT,
            source TEXT NOT NULL,
            url TEXT,
            published_at TIMESTAMP NOT NULL,
            sentiment TEXT,
            is_catalyst BOOLEAN DEFAULT 0,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, headline, published_at)
        )
    ''')
    
    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol ON news(symbol)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_published ON news(published_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_catalyst ON news(is_catalyst, published_at DESC)')
    
    # Watchlist table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watchlist (
            symbol TEXT PRIMARY KEY,
            market_cap REAL,
            float_shares REAL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✓ Database initialized")

def load_watchlist():
    """Load watchlist from database or create from top stocks"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT symbol FROM watchlist')
    watchlist = [row[0] for row in cursor.fetchall()]
    
    if not watchlist:
        print("Creating watchlist from top stocks...")
        # Load from all_stocks_complete.csv
        if os.path.exists('all_stocks_complete.csv'):
            df = pd.read_csv('all_stocks_complete.csv')
            # Sort by market cap, take top N
            df = df.dropna(subset=['market_cap'])
            df = df.sort_values('market_cap', ascending=False).head(WATCHLIST_SIZE)
            
            for _, row in df.iterrows():
                cursor.execute('''
                    INSERT OR IGNORE INTO watchlist (symbol, market_cap, float_shares)
                    VALUES (?, ?, ?)
                ''', (row['symbol'], row.get('market_cap'), row.get('float_shares')))
            
            conn.commit()
            watchlist = df['symbol'].tolist()
            print(f"✓ Created watchlist with {len(watchlist)} stocks")
        else:
            # Default fallback watchlist
            watchlist = ['AAPL', 'TSLA', 'NVDA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'AMD', 'NFLX', 'INTC']
            print(f"⚠ Using default watchlist: {len(watchlist)} stocks")
    
    conn.close()
    return watchlist

def is_catalyst_news(headline, summary):
    """Check if news contains catalyst keywords"""
    text = f"{headline} {summary}".lower()
    return any(keyword in text for keyword in CATALYST_KEYWORDS)

def fetch_benzinga_news(symbols, since_hours=24):
    """Fetch news from Benzinga with pagination"""
    if not BENZINGA_API_KEY:
        return []
    
    news_items = []
    since = datetime.now() - timedelta(hours=since_hours)
    
    try:
        url = 'https://api.benzinga.com/api/v2/news'
        headers = {
            'Accept': 'application/json'
        }
        
        # Paginate through results (Benzinga returns max 25 per page)
        for page in range(10):  # Get up to 10 pages (250 items)
            params = {
                'token': BENZINGA_API_KEY,
                'tickers': ','.join(symbols),
                'dateFrom': since.strftime('%Y-%m-%d'),
                'pageSize': 100,
                'page': page
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if not data:  # No more results
                    break
                    
                for item in data:
                    # Extract stock symbols from stocks field (list of dicts)
                    stock_list = [s.get('name') for s in item.get('stocks', []) if isinstance(s, dict)]
                    for symbol in symbols:
                        if symbol in stock_list:
                            news_items.append({
                                'symbol': symbol,
                                'headline': item.get('title', ''),
                                'summary': item.get('body', '')[:500],
                                'source': 'Benzinga',
                                'url': item.get('url', ''),
                                'published_at': item.get('created', ''),
                                'sentiment': None
                            })
            else:
                break  # Stop on error
                
    except Exception as e:
        print(f"Benzinga error: {e}")
    
    return news_items

def fetch_finnhub_news(symbols, since_hours=24):
    """Fetch news from Finnhub"""
    if not FINNHUB_API_KEY:
        return []
    
    news_items = []
    since = datetime.now() - timedelta(hours=since_hours)
    from_ts = int(since.timestamp())
    to_ts = int(datetime.now().timestamp())
    
    for symbol in symbols:
        try:
            url = 'https://finnhub.io/api/v1/company-news'
            params = {
                'symbol': symbol,
                'from': datetime.fromtimestamp(from_ts).strftime('%Y-%m-%d'),
                'to': datetime.fromtimestamp(to_ts).strftime('%Y-%m-%d'),
                'token': FINNHUB_API_KEY
            }
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                for item in data[:10]:  # Limit per symbol
                    news_items.append({
                        'symbol': symbol,
                        'headline': item.get('headline', ''),
                        'summary': item.get('summary', '')[:500],
                        'source': 'Finnhub',
                        'url': item.get('url', ''),
                        'published_at': datetime.fromtimestamp(item.get('datetime', 0)).isoformat(),
                        'sentiment': item.get('sentiment')
                    })
            
            time.sleep(0.1)  # Rate limit
        except Exception as e:
            print(f"Finnhub error for {symbol}: {e}")
    
    return news_items

def fetch_alpha_vantage_news(symbols):
    """Fetch news from Alpha Vantage"""
    if not ALPHA_VANTAGE_KEY:
        return []
    
    news_items = []
    
    for symbol in symbols[:10]:  # Limit due to rate limits
        try:
            url = 'https://www.alphavantage.co/query'
            params = {
                'function': 'NEWS_SENTIMENT',
                'tickers': symbol,
                'apikey': ALPHA_VANTAGE_KEY
            }
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                for item in data.get('feed', [])[:5]:
                    news_items.append({
                        'symbol': symbol,
                        'headline': item.get('title', ''),
                        'summary': item.get('summary', '')[:500],
                        'source': 'AlphaVantage',
                        'url': item.get('url', ''),
                        'published_at': item.get('time_published', ''),
                        'sentiment': item.get('overall_sentiment_label')
                    })
            
            time.sleep(12)  # 5 req/min = 12s between requests
        except Exception as e:
            print(f"Alpha Vantage error for {symbol}: {e}")
    
    return news_items

def save_news_to_db(news_items):
    """Save news to database, avoiding duplicates"""
    if not news_items:
        return 0
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    saved = 0
    for item in news_items:
        is_catalyst = is_catalyst_news(item['headline'], item.get('summary', ''))
        
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO news 
                (symbol, headline, summary, source, url, published_at, sentiment, is_catalyst)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item['symbol'],
                item['headline'],
                item.get('summary', ''),
                item['source'],
                item.get('url', ''),
                item['published_at'],
                item.get('sentiment'),
                is_catalyst
            ))
            
            if cursor.rowcount > 0:
                saved += 1
        except Exception as e:
            print(f"Error saving news: {e}")
    
    conn.commit()
    conn.close()
    
    return saved

def save_news_to_csv(news_items):
    """Append news to CSV files by source"""
    if not news_items:
        return
    
    # Group by source
    by_source = {}
    for item in news_items:
        source = item['source']
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(item)
    
    # Save each source to separate CSV
    for source, items in by_source.items():
        filename = f'news_{source.lower()}.csv'
        df = pd.DataFrame(items)
        
        # Append to existing file or create new
        import os
        file_exists = os.path.exists(filename)
        df.to_csv(filename, mode='a', header=not file_exists, index=False)
        print(f"  └─ 💾 Saved {len(items)} items to {filename}")

def get_recent_catalysts(hours=24, limit=50):
    """Get recent catalyst news from cache"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    since = datetime.now() - timedelta(hours=hours)
    cursor.execute('''
        SELECT symbol, headline, summary, source, url, published_at
        FROM news
        WHERE is_catalyst = 1 AND published_at >= ?
        ORDER BY published_at DESC
        LIMIT ?
    ''', (since.isoformat(), limit))
    
    results = cursor.fetchall()
    conn.close()
    
    return [
        {
            'symbol': row[0],
            'headline': row[1],
            'summary': row[2],
            'source': row[3],
            'url': row[4],
            'published_at': row[5]
        }
        for row in results
    ]

def cleanup_old_news(days=7):
    """Remove news older than N days"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cutoff = datetime.now() - timedelta(days=days)
    cursor.execute('DELETE FROM news WHERE published_at < ?', (cutoff.isoformat(),))
    deleted = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    if deleted > 0:
        print(f"🗑️  Cleaned up {deleted} old news items")

def monitor_loop():
    """Main monitoring loop"""
    print("=" * 60)
    print("🚀 News Monitor Started")
    print("=" * 60)
    
    init_database()
    watchlist = load_watchlist()
    
    print(f"\n📊 Monitoring {len(watchlist)} stocks")
    print(f"⏱️  Poll interval: {POLL_INTERVAL}s ({POLL_INTERVAL//60} minutes)")
    print(f"📦 Batch size: {BATCH_SIZE} stocks")
    print(f"\nPress Ctrl+C to stop\n")
    
    iteration = 0
    
    try:
        while True:
            iteration += 1
            start_time = time.time()
            
            print(f"\n{'='*60}")
            print(f"🔄 Iteration #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}")
            
            total_news = 0
            
            # Process watchlist in batches
            for i in range(0, len(watchlist), BATCH_SIZE):
                batch = watchlist[i:i+BATCH_SIZE]
                batch_num = i // BATCH_SIZE + 1
                total_batches = (len(watchlist) + BATCH_SIZE - 1) // BATCH_SIZE
                
                print(f"\n📦 Batch {batch_num}/{total_batches} ({len(batch)} stocks)")
                
                # Fetch from all sources
                all_news = []
                
                # Benzinga (disabled - limited coverage, editorial only)
                # if BENZINGA_API_KEY:
                #     print("  └─ Fetching from Benzinga...")
                #     benzinga_news = fetch_benzinga_news(batch, since_hours=168)  # 7 days
                #     all_news.extend(benzinga_news)
                #     print(f"     ✓ {len(benzinga_news)} items")
                
                # Finnhub (good coverage)
                if FINNHUB_API_KEY:
                    print("  └─ Fetching from Finnhub...")
                    finnhub_news = fetch_finnhub_news(batch, since_hours=168)  # 7 days
                    all_news.extend(finnhub_news)
                    print(f"     ✓ {len(finnhub_news)} items")
                
                # Alpha Vantage (rate limited, skip for now)
                # if ALPHA_VANTAGE_KEY and batch_num == 1:
                #     alpha_news = fetch_alpha_vantage_news(batch[:5])
                #     all_news.extend(alpha_news)
                
                # Save to database
                if all_news:
                    saved = save_news_to_db(all_news)
                    save_news_to_csv(all_news)  # Also save to CSV
                    total_news += saved
                    if saved > 0:
                        print(f"  └─ 💾 Saved {saved} new items")
                
                # Rate limit between batches
                time.sleep(2)
            
            # Show catalysts
            print(f"\n📰 Total new news items: {total_news}")
            
            catalysts = get_recent_catalysts(hours=1, limit=10)
            if catalysts:
                print(f"\n🎯 Recent Catalysts (last hour):")
                for cat in catalysts[:5]:
                    print(f"  • {cat['symbol']}: {cat['headline'][:80]}")
            
            # Cleanup old news
            cleanup_old_news(days=7)
            
            # Calculate sleep time
            elapsed = time.time() - start_time
            sleep_time = max(0, POLL_INTERVAL - elapsed)
            
            print(f"\n⏸️  Next update in {sleep_time:.0f}s ({sleep_time/60:.1f}m)")
            time.sleep(sleep_time)
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Monitor stopped by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        raise

if __name__ == '__main__':
    monitor_loop()
