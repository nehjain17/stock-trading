#!/usr/bin/env python3
"""
Moomoo Data Fetcher
Fetches real-time market data from Moomoo OpenAPI
Input: low_float_stocks_*.csv, all_stocks_complete.csv
Output: data/moomoo_market_data.csv
"""
import pandas as pd
from moomoo import OpenQuoteContext, RET_OK
import time
from datetime import datetime
import argparse
import os

# Configuration
MOOMOO_HOST = '127.0.0.1'
MOOMOO_PORT = 11111
OUTPUT_FILE = '../output/moomoo_market_data.csv'
DELAY = 0.3  # seconds between requests

class MoomooFetcher:
    def __init__(self, input_file, max_stocks=None):
        self.input_file = input_file
        self.max_stocks = max_stocks
        self.quote_ctx = None
        self.results = []
        
    def connect(self):
        """Connect to Moomoo OpenD"""
        try:
            self.quote_ctx = OpenQuoteContext(host=MOOMOO_HOST, port=MOOMOO_PORT)
            print(f"✓ Connected to Moomoo OpenD on {MOOMOO_HOST}:{MOOMOO_PORT}")
            return True
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            print("  Make sure OpenD is running!")
            return False
    
    def fetch_stock(self, symbol, float_shares=None, market_cap=None):
        """Fetch data for a single stock"""
        try:
            code = f'US.{symbol}'
            
            # Get snapshot
            ret, data = self.quote_ctx.get_market_snapshot([code])
            
            if ret != RET_OK:
                return None
            
            if len(data) == 0:
                return None
            
            row = data.iloc[0]
            
            return {
                'symbol': symbol,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'last_price': row.get('last_price'),
                'open_price': row.get('open_price'),
                'high_price': row.get('high_price'),
                'low_price': row.get('low_price'),
                'prev_close': row.get('prev_close_price'),
                'volume': row.get('volume'),
                'turnover': row.get('turnover'),
                'float_shares': float_shares,
                'market_cap': market_cap
            }
            
        except Exception as e:
            return None
    
    def process(self):
        """Process all stocks from input file"""
        print(f"\n{'='*70}")
        print(f"Moomoo Data Fetcher")
        print(f"{'='*70}\n")
        
        # Load stocks
        df = pd.read_csv(self.input_file)
        if self.max_stocks:
            df = df.head(self.max_stocks)
        
        print(f"Input: {self.input_file}")
        print(f"Stocks: {len(df)}")
        print(f"Output: {OUTPUT_FILE}\n")
        
        if not self.connect():
            print("✗ Cannot proceed without Moomoo connection")
            print("  Note: You may need US market permissions enabled")
            return None
        
        successful = 0
        failed = 0
        
        for idx, row in df.iterrows():
            symbol = row['symbol']
            float_shares = row.get('float', None)
            market_cap = row.get('marketCap', None)
            
            if (idx + 1) % 10 == 0:
                print(f"Progress: {idx + 1}/{len(df)} | ✓ {successful} | ✗ {failed}")
            
            data = self.fetch_stock(symbol, float_shares, market_cap)
            
            if data:
                self.results.append(data)
                successful += 1
            else:
                failed += 1
            
            time.sleep(DELAY)
        
        # Save results
        os.makedirs('../output', exist_ok=True)
        result_df = pd.DataFrame(self.results)
        result_df.to_csv(OUTPUT_FILE, index=False)
        
        print(f"\n{'='*70}")
        print(f"✓ Complete!")
        print(f"  Successful: {successful}")
        print(f"  Failed: {failed}")
        print(f"  Output: {OUTPUT_FILE}")
        print(f"{'='*70}\n")
        
        if self.quote_ctx:
            self.quote_ctx.close()
        
        return result_df

def main():
    parser = argparse.ArgumentParser(description='Fetch Moomoo market data')
    parser.add_argument('--input', default='../input/low_float_stocks_100M.csv', help='Input CSV file')
    parser.add_argument('--limit', type=int, help='Limit number of stocks')
    args = parser.parse_args()
    
    fetcher = MoomooFetcher(args.input, args.limit)
    fetcher.process()

if __name__ == '__main__':
    main()
