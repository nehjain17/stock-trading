#!/usr/bin/env python3
"""
Fetch Benzinga news for all stocks sequentially
"""
import os
import time
import requests
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Configuration
BENZINGA_API_KEY = os.getenv('BENZINGA_API_KEY')
DB_PATH = 'news_cache.db'
STOCKS_FILE = 'all_stocks_complete.csv'
DELAY_BETWEEN_REQUESTS = 0.5  # 500ms delay to avoid rate limits
LOOKBACK_DAYS = 2

def fetch_benzinga_for_symbol(symbol, since_days=7):
    """Fetch Benzinga news for a single symbol with pagination"""
    if not BENZINGA_API_KEY:
        return [], None
    
    news_items = []
    error_msg = None
    since = datetime.now() - timedelta(days=since_days)
    
    try:
        url = 'https://api.benzinga.com/api/v2/news'
        headers = {'Accept': 'application/json'}
        
        # Paginate through results (max 25 per page)
        for page in range(10):  # Up to 10 pages (250 items)
            params = {
                'token': BENZINGA_API_KEY,
                'tickers': symbol,
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
                    news_items.append({
                        'symbol': symbol,
                        'headline': item.get('title', ''),
                        'summary': item.get('body', '')[:500],
                        'source': 'Benzinga',
                        'url': item.get('url', ''),
                        'published_at': item.get('created', ''),
                        'is_catalyst': 0,  # Will be updated later
                        'sentiment': None
                    })
            elif response.status_code == 429:
                error_msg = "Rate limit (429)"
                print(f"    ⚠️  Rate limited (429), waiting 5s...")
                time.sleep(5)
                continue
            else:
                error_msg = f"HTTP {response.status_code}"
                print(f"    ⚠️  HTTP {response.status_code}")
                break
                
    except Exception as e:
        error_msg = str(e)
        print(f"    ❌ Error: {e}")
    
    return news_items, error_msg

def save_news_to_db(news_items):
    """Save news items to database"""
    if not news_items:
        return 0
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    saved = 0
    for item in news_items:
        try:
            # Check for catalyst keywords
            text = f"{item['headline']} {item['summary']}".lower()
            catalyst_keywords = [
                'halted', 'halt', 'resume', 'resumption',
                'breakthrough', 'approval', 'fda',
                'merger', 'acquisition', 'buyout',
                'earnings beat', 'earnings miss',
                'guidance raised', 'guidance lowered',
                'short squeeze', 'gamma squeeze',
                'offering', 'dilution', 'direct offering',
                'contract', 'deal', 'partnership'
            ]
            item['is_catalyst'] = 1 if any(kw in text for kw in catalyst_keywords) else 0
            
            cursor.execute('''
                INSERT OR REPLACE INTO news 
                (symbol, headline, summary, source, url, published_at, is_catalyst, sentiment)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item['symbol'],
                item['headline'],
                item['summary'],
                item['source'],
                item['url'],
                item['published_at'],
                item['is_catalyst'],
                item['sentiment']
            ))
            saved += 1
        except Exception as e:
            print(f"    DB error: {e}")
    
    conn.commit()
    conn.close()
    return saved

def save_news_to_csv(news_items, filename='benzinga_all_stocks_news.csv'):
    """Append news items to CSV file"""
    if not news_items:
        return
    
    df = pd.DataFrame(news_items)
    
    # Check if file exists
    if os.path.exists(filename):
        # Append without header
        df.to_csv(filename, mode='a', header=False, index=False)
    else:
        # Create new with header
        df.to_csv(filename, mode='w', header=True, index=False)

def main():
    print("=" * 80)
    print("BENZINGA NEWS FETCHER - ALL STOCKS")
    print("=" * 80)
    
    # Load all stocks
    if not os.path.exists(STOCKS_FILE):
        print(f"❌ Error: {STOCKS_FILE} not found")
        return
    
    df = pd.read_csv(STOCKS_FILE)
    total_stocks = len(df)
    print(f"\n📊 Loaded {total_stocks:,} stocks from {STOCKS_FILE}")
    print(f"⏱️  Delay between requests: {DELAY_BETWEEN_REQUESTS}s")
    print(f"📅 Looking back: {LOOKBACK_DAYS} days")
    
    # Estimate time
    estimated_seconds = total_stocks * DELAY_BETWEEN_REQUESTS
    estimated_hours = estimated_seconds / 3600
    print(f"⏰ Estimated time: {estimated_hours:.1f} hours")
    
    input("\nPress Enter to start or Ctrl+C to cancel...")
    
    # Process each stock
    start_time = time.time()
    total_news = 0
    stocks_with_news = 0
    errors = []
    
    for idx, row in df.iterrows():
        symbol = row['symbol']
        progress = (idx + 1) / total_stocks * 100
        
        print(f"\n[{idx+1}/{total_stocks}] ({progress:.1f}%) {symbol}", end='')
        
        # Fetch news
        news, error = fetch_benzinga_for_symbol(symbol, LOOKBACK_DAYS)
        
        if error:
            errors.append({'symbol': symbol, 'error': error})
        
        if news:
            # Save to database
            saved = save_news_to_db(news)
            # Save to CSV
            save_news_to_csv(news)
            total_news += saved
            stocks_with_news += 1
            print(f" - ✓ {len(news)} items ({saved} saved)")
        else:
            if error:
                print(f" - ❌ Failed: {error}")
            else:
                print(" - No news")
        
        # Progress update every 100 stocks
        if (idx + 1) % 100 == 0:
            elapsed = time.time() - start_time
            rate = (idx + 1) / elapsed
            remaining = (total_stocks - idx - 1) / rate
            print(f"\n    📈 Progress: {stocks_with_news} stocks with news, {total_news} total items, {len(errors)} errors")
            print(f"    ⏱️  Time remaining: {remaining/3600:.1f} hours")
        
        # Rate limiting
        time.sleep(DELAY_BETWEEN_REQUESTS)
    
    # Summary
    elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print("✅ COMPLETE")
    print("=" * 80)
    print(f"Total stocks processed: {total_stocks:,}")
    print(f"Stocks with news: {stocks_with_news:,} ({stocks_with_news/total_stocks*100:.1f}%)")
    print(f"Total news items: {total_news:,}")
    print(f"Total errors: {len(errors):,}")
    print(f"Time taken: {elapsed/3600:.2f} hours")
    print(f"Average: {elapsed/total_stocks:.2f}s per stock")
    
    # Save errors to file
    if errors:
        print(f"\n⚠️  Saving {len(errors)} errors to benzinga_errors.csv")
        error_df = pd.DataFrame(errors)
        error_df.to_csv('benzinga_errors.csv', index=False)
        print(f"   Top 10 errors:")
        error_counts = error_df['error'].value_counts()
        for error, count in error_counts.head(10).items():
            print(f"   - {error}: {count} times")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
