#!/usr/bin/env python3
"""
Fetch Finnhub news for low float stocks (< 10M) and measure timing
"""
import pandas as pd
import sqlite3
import requests
import os
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY')
BATCH_SIZE = 50
DELAY_BETWEEN_STOCKS = 0.1  # seconds
DELAY_BETWEEN_BATCHES = 0.5  # seconds

def fetch_finnhub_news(symbol, days=7):
    """Fetch news for a symbol from Finnhub"""
    url = 'https://finnhub.io/api/v1/company-news'
    from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    to_date = datetime.now().strftime('%Y-%m-%d')
    
    params = {
        'symbol': symbol,
        'from': from_date,
        'to': to_date,
        'token': FINNHUB_API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return []

def main():
    print("Loading low float stocks (< 10M)...")
    df = pd.read_csv('low_float_stocks_10M.csv')
    symbols = df['symbol'].tolist()
    
    print(f"\nTotal symbols: {len(symbols)}")
    print(f"Batch size: {BATCH_SIZE}")
    print(f"Delay between stocks: {DELAY_BETWEEN_STOCKS}s")
    print(f"Delay between batches: {DELAY_BETWEEN_BATCHES}s")
    
    total_batches = (len(symbols) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"Total batches: {total_batches}")
    
    # Estimate time
    time_per_batch = (BATCH_SIZE * DELAY_BETWEEN_STOCKS) + DELAY_BETWEEN_BATCHES
    estimated_time = total_batches * time_per_batch
    print(f"\nEstimated time: {estimated_time/60:.1f} minutes ({estimated_time:.0f} seconds)")
    
    input("\nPress Enter to start fetching news...")
    
    # Initialize database
    conn = sqlite3.connect('news_cache.db')
    cursor = conn.cursor()
    
    # Create table if not exists
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            headline TEXT NOT NULL,
            summary TEXT,
            source TEXT NOT NULL,
            url TEXT,
            published_at TEXT NOT NULL,
            is_catalyst INTEGER DEFAULT 0,
            sentiment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, url)
        )
    ''')
    
    start_time = time.time()
    total_news = 0
    stocks_with_news = 0
    
    print(f"\n{'='*60}")
    print("Starting news fetch...")
    print(f"{'='*60}\n")
    
    for batch_num in range(total_batches):
        batch_start = batch_num * BATCH_SIZE
        batch_end = min((batch_num + 1) * BATCH_SIZE, len(symbols))
        batch_symbols = symbols[batch_start:batch_end]
        
        batch_time = time.time()
        batch_news = 0
        
        for symbol in batch_symbols:
            news = fetch_finnhub_news(symbol)
            
            if news:
                stocks_with_news += 1
                for item in news:
                    try:
                        cursor.execute('''
                            INSERT OR IGNORE INTO news 
                            (symbol, headline, summary, source, url, published_at, is_catalyst)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            symbol,
                            item.get('headline', ''),
                            item.get('summary', ''),
                            'Finnhub',
                            item.get('url', ''),
                            datetime.fromtimestamp(item.get('datetime', 0)).isoformat(),
                            0
                        ))
                        batch_news += 1
                        total_news += 1
                    except Exception as e:
                        pass
            
            time.sleep(DELAY_BETWEEN_STOCKS)
        
        conn.commit()
        
        elapsed = time.time() - start_time
        batch_elapsed = time.time() - batch_time
        progress = (batch_end / len(symbols)) * 100
        
        print(f"Batch {batch_num+1}/{total_batches} | "
              f"Stocks {batch_start+1}-{batch_end}/{len(symbols)} | "
              f"News: {batch_news} | "
              f"Time: {batch_elapsed:.1f}s | "
              f"Progress: {progress:.1f}% | "
              f"Elapsed: {elapsed/60:.1f}m")
        
        time.sleep(DELAY_BETWEEN_BATCHES)
    
    conn.close()
    
    total_time = time.time() - start_time
    
    print(f"\n{'='*60}")
    print("COMPLETED!")
    print(f"{'='*60}")
    print(f"Total time: {total_time/60:.2f} minutes ({total_time:.0f} seconds)")
    print(f"Total news items: {total_news}")
    print(f"Stocks with news: {stocks_with_news}/{len(symbols)} ({stocks_with_news/len(symbols)*100:.1f}%)")
    print(f"Average time per stock: {total_time/len(symbols):.2f}s")
    print(f"Average time per batch: {total_time/total_batches:.1f}s")

if __name__ == '__main__':
    main()
