#!/usr/bin/env python3
"""
Fetch stock data for US stocks with smart rate limiting.
Uses the symbol list and fetches data in batches with delays.
"""
import pandas as pd
import yfinance as yf
import time
import argparse

def fetch_stock_data_batch(symbols, delay=0.5):
    """Fetch stock data with rate limiting"""
    results = []
    total = len(symbols)
    
    for i, symbol in enumerate(symbols, 1):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            if info and 'symbol' in info:
                results.append({
                    'symbol': symbol,
                    'name': info.get('longName') or info.get('shortName'),
                    'exchange': info.get('exchange'),
                    'market_cap': info.get('marketCap'),
                    'share_outstanding': info.get('sharesOutstanding'),
                    'float_shares': info.get('floatShares'),
                    'sector': info.get('sector'),
                    'industry': info.get('industry'),
                    'country': info.get('country'),
                    'currency': info.get('currency'),
                })
            
            if i % 50 == 0:
                print(f"Processed {i}/{total} ({i*100//total}%)")
            
            time.sleep(delay)
            
        except Exception as e:
            if i % 50 == 0:
                print(f"Processed {i}/{total} ({i*100//total}%) - errors: {e}")
            time.sleep(delay)
            continue
    
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbols', default='us_stock_symbols.csv',
                        help='CSV file with symbol list')
    parser.add_argument('--out', default='all_us_stocks_complete.csv')
    parser.add_argument('--max-float', type=int, default=None)
    parser.add_argument('--delay', type=float, default=0.5,
                        help='Delay between requests (seconds)')
    args = parser.parse_args()

    # Load symbols
    print(f"Loading symbols from {args.symbols}...")
    symbols_df = pd.read_csv(args.symbols)
    symbols = symbols_df['symbol'].tolist()
    print(f"Found {len(symbols)} symbols")
    
    print(f"\nFetching data with {args.delay}s delay...")
    print(f"Estimated time: ~{len(symbols) * args.delay / 60:.0f} minutes\n")
    
    results = fetch_stock_data_batch(symbols, delay=args.delay)
    
    print(f"\n\nSuccessfully fetched data for {len(results)} stocks")
    
    if not results:
        print("No data fetched!")
        return
    
    # Create DataFrame
    df = pd.DataFrame(results)
    
    # Filter if requested
    if args.max_float:
        df_filtered = df[df['share_outstanding'].notnull() & (df['share_outstanding'] <= args.max_float)].copy()
        print(f"Filtered to {len(df_filtered)} stocks with shares outstanding <= {args.max_float:,}")
        df = df_filtered
    
    # Sort by symbol
    df = df.sort_values('symbol')
    
    # Save
    df.to_csv(args.out, index=False)
    print(f"\nSaved to {args.out}")
    
    # Show summary
    print(f"\nSummary:")
    print(f"Total stocks: {len(df)}")
    print(f"With market cap: {df['market_cap'].notnull().sum()}")
    print(f"With shares outstanding: {df['share_outstanding'].notnull().sum()}")
    print(f"With float shares: {df['float_shares'].notnull().sum()}")

if __name__ == '__main__':
    main()
