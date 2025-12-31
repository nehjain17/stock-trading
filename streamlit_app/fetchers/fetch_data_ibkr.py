#!/usr/bin/env python3
"""
IBKR Data Fetcher
Fetches real-time market data from Interactive Brokers
Input: low_float_stocks_*.csv, all_stocks_complete.csv
Output: data/ibkr_market_data.csv
"""
import pandas as pd
from ib_insync import IB, Stock
import time
from datetime import datetime
import argparse
import os

# Configuration
IBKR_HOST = '127.0.0.1'
IBKR_PORT = 7496
OUTPUT_FILE = '../output/ibkr_market_data.csv'
DELAY = 0.5  # seconds between requests

class IBKRFetcher:
    def __init__(self, input_file, max_stocks=None):
        self.input_file = input_file
        self.max_stocks = max_stocks
        self.ib = IB()
        self.results = []
        
    def connect(self):
        """Connect to IBKR TWS/Gateway"""
        try:
            self.ib.connect(IBKR_HOST, IBKR_PORT, clientId=888, readonly=True)
            self.ib.RequestTimeout = 5
            self.ib.reqMarketDataType(3)  # Delayed data
            print(f"✓ Connected to IBKR on {IBKR_HOST}:{IBKR_PORT}")
            return True
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False
    
    def fetch_stock(self, symbol, float_shares=None, market_cap=None):
        """Fetch data for a single stock"""
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            qualified = self.ib.qualifyContracts(contract)
            
            if not qualified:
                return None
            
            # Request market data
            ticker = self.ib.reqMktData(qualified[0], '236', False, False)
            self.ib.sleep(2)
            
            data = {
                'symbol': symbol,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'last_price': ticker.last if ticker.last else None,
                'bid': ticker.bid if ticker.bid else None,
                'ask': ticker.ask if ticker.ask else None,
                'volume': ticker.volume if ticker.volume else None,
                'bid_size': ticker.bidSize if ticker.bidSize else None,
                'ask_size': ticker.askSize if ticker.askSize else None,
                'high': ticker.high if ticker.high else None,
                'low': ticker.low if ticker.low else None,
                'close': ticker.close if ticker.close else None,
                'float_shares': float_shares,
                'market_cap': market_cap,
                'exchange': qualified[0].primaryExchange
            }
            
            self.ib.cancelMktData(qualified[0])
            return data
            
        except Exception as e:
            return None
    
    def process(self):
        """Process all stocks from input file"""
        print(f"\n{'='*70}")
        print(f"IBKR Data Fetcher")
        print(f"{'='*70}\n")
        
        # Load stocks
        df = pd.read_csv(self.input_file)
        if self.max_stocks:
            df = df.head(self.max_stocks)
        
        print(f"Input: {self.input_file}")
        print(f"Stocks: {len(df)}")
        print(f"Output: {OUTPUT_FILE}\n")
        
        if not self.connect():
            return
        
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
        
        self.ib.disconnect()
        return result_df

def main():
    parser = argparse.ArgumentParser(description='Fetch IBKR market data')
    parser.add_argument('--input', default='../input/low_float_stocks_100M.csv', help='Input CSV file')
    parser.add_argument('--limit', type=int, help='Limit number of stocks')
    args = parser.parse_args()
    
    fetcher = IBKRFetcher(args.input, args.limit)
    fetcher.process()

if __name__ == '__main__':
    main()
