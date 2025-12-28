#!/usr/bin/env python3
"""
Fetch all legitimate US stocks (NASDAQ, NYSE, AMEX) using Yahoo Finance.
This filters out warrants, units, preferred shares, and OTC stocks.
"""
import pandas as pd
import yfinance as yf
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_nasdaq_stocks():
    """Fetch NASDAQ listed stocks from NASDAQ's FTP"""
    try:
        url = 'ftp://ftp.nasdaqtrader.com/symboldirectory/nasdaqlisted.txt'
        df = pd.read_csv(url, sep='|')
        df = df[df['Test Issue'] == 'N']  # Exclude test issues
        # Filter normal status (handle NaN values)
        df = df[df['Financial Status'].fillna('N') == 'N']
        df = df[df['Market Category'].isin(['Q', 'G', 'S'])]  # Global Select, Global, Capital markets
        symbols = df['Symbol'].tolist()
        # Filter out units, warrants, preferred - be more aggressive
        symbols = [s for s in symbols if isinstance(s, str) and not any(x in s for x in ['$', '.', '^', '-']) and len(s) <= 5 and s.isalpha()]
        return symbols
    except Exception as e:
        print(f"Error fetching NASDAQ stocks: {e}")
        return []

def get_nyse_stocks():
    """Fetch NYSE and other exchange stocks from NASDAQ's FTP"""
    try:
        url = 'ftp://ftp.nasdaqtrader.com/symboldirectory/otherlisted.txt'
        df = pd.read_csv(url, sep='|')
        df = df[df['Test Issue'] == 'N']  # Exclude test issues
        # Filter for NYSE, AMEX, ARCA
        df = df[df['Exchange'].isin(['N', 'A', 'P'])]  # N=NYSE, A=AMEX/NYSE American, P=ARCA
        symbols = df['ACT Symbol'].tolist()
        # Filter out units, warrants, preferred - be more aggressive
        symbols = [s for s in symbols if isinstance(s, str) and not any(x in s for x in ['$', '.', '^', '-', '+']) and len(s) <= 5 and s.replace(' ', '').isalpha()]
        return symbols
    except Exception as e:
        print(f"Error fetching NYSE stocks: {e}")
        return []

def fetch_stock_data(symbol):
    """Fetch stock data from Yahoo Finance"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # Basic validation
        if not info or 'symbol' not in info:
            return None
            
        return {
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
        }
    except Exception as e:
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='us_stocks_complete.csv')
    parser.add_argument('--max-float', type=int, default=None,
                        help='Maximum shares outstanding to include')
    parser.add_argument('--threads', type=int, default=10,
                        help='Number of concurrent threads')
    args = parser.parse_args()

    print("Fetching stock lists from NASDAQ FTP...")
    nasdaq_symbols = get_nasdaq_stocks()
    print(f"Found {len(nasdaq_symbols)} NASDAQ stocks")
    
    nyse_symbols = get_nyse_stocks()
    print(f"Found {len(nyse_symbols)} NYSE/AMEX stocks")
    
    all_symbols = list(set(nasdaq_symbols + nyse_symbols))
    all_symbols.sort()
    print(f"\nTotal unique symbols: {len(all_symbols)}")
    print(f"Fetching data from Yahoo Finance using {args.threads} threads...")
    print("This will take approximately 5-10 minutes...\n")
    
    results = []
    completed = 0
    
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        future_to_symbol = {executor.submit(fetch_stock_data, symbol): symbol for symbol in all_symbols}
        
        for future in as_completed(future_to_symbol):
            completed += 1
            if completed % 100 == 0:
                print(f"Processed {completed}/{len(all_symbols)} ({completed*100//len(all_symbols)}%)")
            
            result = future.result()
            if result:
                results.append(result)
    
    print(f"\nSuccessfully fetched data for {len(results)} stocks")
    
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
