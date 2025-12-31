#!/usr/bin/env python3
"""
Finnhub News Fetcher
Fetches news from Finnhub API (individual calls only)
Input: low_float_stocks_*.csv, all_stocks_complete.csv
Output: data/finnhub_news.csv
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
API_KEY = os.getenv('FINNHUB_API_KEY')
API_URL = 'https://finnhub.io/api/v1/company-news'
OUTPUT_FILE = '../output/finnhub_news.csv'
DELAY = 1.1  # Rate limit: 60 calls/min

class FinnhubFetcher:
    def __init__(self, input_file, days_back=7, max_stocks=None):
        self.input_file = input_file
        self.days_back = days_back
        self.max_stocks = max_stocks
        self.results = []
        
    def fetch_stock(self, symbol):
        """Fetch news for a single stock"""
        try:
            from_date = (datetime.now() - timedelta(days=self.days_back)).strftime('%Y-%m-%d')
            to_date = datetime.now().strftime('%Y-%m-%d')
            
            params = {
                'symbol': symbol,
                'from': from_date,
                'to': to_date,
                'token': API_KEY
            }
            
            response = requests.get(API_URL, params=params, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                return []
        except Exception as e:
            return []
    
    def process(self):
        """Process all stocks from input file"""
        print(f"\n{'='*70}")
        print(f"Finnhub News Fetcher")
        print(f"{'='*70}\n")
        
        # Load stocks
        df = pd.read_csv(self.input_file)
        if self.max_stocks:
            df = df.head(self.max_stocks)
        
        symbols = df['symbol'].tolist()
        
        print(f"Input: {self.input_file}")
        print(f"Stocks: {len(symbols)}")
        print(f"Days back: {self.days_back}")
        print(f"Output: {OUTPUT_FILE}\n")
        
        successful = 0
        failed = 0
        
        for idx, symbol in enumerate(symbols):
            if (idx + 1) % 10 == 0:
                print(f"Progress: {idx + 1}/{len(symbols)} | ✓ {successful} | ✗ {failed}")
            
            news = self.fetch_stock(symbol)
            
            if news:
                for item in news:
                    self.results.append({
                        'symbol': sanitize_text(symbol, max_len=16),
                        'timestamp': sanitize_text(datetime.fromtimestamp(item.get('datetime', 0)).strftime('%Y-%m-%d %H:%M:%S'), max_len=64),
                        'title': sanitize_text(item.get('headline', ''), max_len=300),
                        'url': safe_url(item.get('url', '')),
                        'source': 'Finnhub'
                    })
                successful += 1
            else:
                failed += 1
            
            time.sleep(DELAY)
        
        # Save results
        os.makedirs('../output', exist_ok=True)
        result_df = pd.DataFrame(self.results)
        
        if len(result_df) > 0:
            result_df = result_df.drop_duplicates(subset=['symbol', 'title', 'timestamp'])
            result_df.to_csv(OUTPUT_FILE, index=False)
        
        print(f"\n{'='*70}")
        print(f"✓ Complete!")
        print(f"  Successful: {successful}")
        print(f"  Failed: {failed}")
        print(f"  Total news items: {len(result_df)}")
        print(f"  Output: {OUTPUT_FILE}")
        print(f"{'='*70}\n")
        
        return result_df

def main():
    parser = argparse.ArgumentParser(description='Fetch Finnhub news')
    parser.add_argument('--input', default='../input/low_float_stocks_100M.csv', help='Input CSV file')
    parser.add_argument('--days', type=int, default=7, help='Days back to fetch news')
    parser.add_argument('--limit', type=int, help='Limit number of stocks')
    args = parser.parse_args()
    
    fetcher = FinnhubFetcher(args.input, args.days, args.limit)
    fetcher.process()

if __name__ == '__main__':
    main()
