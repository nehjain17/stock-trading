#!/usr/bin/env python3
"""
Yahoo Finance Data Fetcher
Fetches market data from Yahoo Finance (best OTC/Pink Sheet coverage)
Input: low_float_stocks_*.csv, all_stocks_complete.csv
Output: data/yahoo_market_data.csv
"""
import pandas as pd
import yfinance as yf
import time
from datetime import datetime
import argparse
import os

# Configuration
OUTPUT_FILE = '../output/yahoo_market_data.csv'
DELAY = 0.2  # Yahoo has no strict rate limit

class YahooFetcher:
    def __init__(self, input_file, max_stocks=None):
        self.input_file = input_file
        self.max_stocks = max_stocks
        self.results = []
        
    def fetch_stock(self, symbol, float_shares=None, market_cap_csv=None):
        """Fetch data for a single stock"""
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            hist = stock.history(period='1d')
            
            if len(hist) == 0:
                return None
            
            latest = hist.iloc[-1]
            
            return {
                'symbol': symbol,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'last_price': latest['Close'],
                'open': latest['Open'],
                'high': latest['High'],
                'low': latest['Low'],
                'volume': latest['Volume'],
                'market_cap': info.get('marketCap', market_cap_csv),
                'float_shares': info.get('floatShares', float_shares),
                'short_ratio': info.get('shortRatio'),
                'short_percent_float': info.get('shortPercentOfFloat'),
                'shares_outstanding': info.get('sharesOutstanding'),
                'avg_volume': info.get('averageVolume'),
                'fifty_two_week_high': info.get('fiftyTwoWeekHigh'),
                'fifty_two_week_low': info.get('fiftyTwoWeekLow')
            }
            
        except Exception as e:
            return None
    
    def process(self):
        """Process all stocks from input file"""
        print(f"\n{'='*70}")
        print(f"Yahoo Finance Data Fetcher")
        print(f"{'='*70}\n")
        
        # Load stocks
        df = pd.read_csv(self.input_file)
        if self.max_stocks:
            df = df.head(self.max_stocks)
        
        print(f"Input: {self.input_file}")
        print(f"Stocks: {len(df)}")
        print(f"Output: {OUTPUT_FILE}\n")
        
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
        
        return result_df

def main():
    parser = argparse.ArgumentParser(description='Fetch Yahoo Finance data')
    parser.add_argument('--input', default='../input/low_float_stocks_100M.csv', help='Input CSV file')
    parser.add_argument('--limit', type=int, help='Limit number of stocks')
    args = parser.parse_args()
    
    fetcher = YahooFetcher(args.input, args.limit)
    fetcher.process()

if __name__ == '__main__':
    main()
