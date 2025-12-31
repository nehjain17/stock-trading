#!/usr/bin/env python3
"""
Benzinga News Fetcher
Fetches news from Benzinga API (bulk capable: 50 stocks per call)
Input: low_float_stocks_*.csv, all_stocks_complete.csv
Output: data/benzinga_news.csv
"""
import pandas as pd
import requests
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import time
import argparse
try:
    from utils.security import sanitize_text, safe_url
except Exception:
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from utils.security import sanitize_text, safe_url

load_dotenv()

# Configuration
API_KEY = os.getenv('BENZINGA_API_KEY')
API_URL = 'https://api.benzinga.com/api/v2/news'
OUTPUT_FILE = '../output/benzinga_news.csv'
BATCH_SIZE = 50  # Benzinga supports bulk requests
DELAY = 1.2  # Rate limit: 60 calls/min

class BenzingaFetcher:
    def __init__(self, input_file, days_back=7, max_stocks=None):
        self.input_file = input_file
        self.days_back = days_back
        self.max_stocks = max_stocks
        self.results = []
        
    def fetch_batch(self, symbols):
        """Fetch news for a batch of symbols"""
        try:
            params = {
                'token': API_KEY,
                'tickers': ','.join(symbols),
                'dateFrom': (datetime.now() - timedelta(days=self.days_back)).strftime('%Y-%m-%d'),
                'pageSize': 100
            }
            headers = {'Accept': 'application/json'}
            
            response = requests.get(API_URL, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"  ✗ Error {response.status_code}")
                return []
        except Exception as e:
            print(f"  ✗ Error: {e}")
            return []
    
    def process(self):
        """Process all stocks from input file"""
        print(f"\n{'='*70}")
        print(f"Benzinga News Fetcher")
        print(f"{'='*70}\n")
        
        # Load stocks
        df = pd.read_csv(self.input_file)
        if self.max_stocks:
            df = df.head(self.max_stocks)
        
        symbols = df['symbol'].tolist()
        
        print(f"Input: {self.input_file}")
        print(f"Stocks: {len(symbols)}")
        print(f"Days back: {self.days_back}")
        print(f"Batch size: {BATCH_SIZE}")
        print(f"Output: {OUTPUT_FILE}\n")
        
        # Process in batches
        total_batches = (len(symbols) + BATCH_SIZE - 1) // BATCH_SIZE
        
        for i in range(0, len(symbols), BATCH_SIZE):
            batch = symbols[i:i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1
            
            print(f"Batch {batch_num}/{total_batches}: {len(batch)} symbols...", end=' ')
            
            news = self.fetch_batch(batch)
            
            for item in news:
                for stock in item.get('stocks', []):
                    self.results.append({
                        'symbol': sanitize_text(stock.get('name', ''), max_len=16),
                        'timestamp': sanitize_text(item.get('created', ''), max_len=64),
                        'title': sanitize_text(item.get('title', ''), max_len=300),
                        'url': safe_url(item.get('url', '')),
                        'source': 'Benzinga'
                    })
            
            print(f"✓ {len(news)} articles")
            time.sleep(DELAY)
        
        # Save results
        os.makedirs('../output', exist_ok=True)
        result_df = pd.DataFrame(self.results)
        
        if len(result_df) > 0:
            # Remove duplicates
            result_df = result_df.drop_duplicates(subset=['symbol', 'title', 'timestamp'])
            result_df.to_csv(OUTPUT_FILE, index=False)
        
        print(f"\n{'='*70}")
        print(f"✓ Complete!")
        print(f"  Total news items: {len(result_df)}")
        print(f"  Unique stocks: {result_df['symbol'].nunique() if len(result_df) > 0 else 0}")
        print(f"  Output: {OUTPUT_FILE}")
        print(f"{'='*70}\n")
        
        return result_df

def main():
    parser = argparse.ArgumentParser(description='Fetch Benzinga news')
    parser.add_argument('--input', default='../input/low_float_stocks_100M.csv', help='Input CSV file')
    parser.add_argument('--days', type=int, default=7, help='Days back to fetch news')
    parser.add_argument('--limit', type=int, help='Limit number of stocks')
    args = parser.parse_args()
    
    fetcher = BenzingaFetcher(args.input, args.days, args.limit)
    fetcher.process()

if __name__ == '__main__':
    main()
