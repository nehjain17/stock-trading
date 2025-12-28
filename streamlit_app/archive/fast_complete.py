#!/usr/bin/env python3
"""
Fast parallel fetch of missing stock data using threading.
"""
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

def fetch_stock(symbol):
    """Fetch single stock data"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        if info and 'symbol' in info:
            return {
                'symbol': symbol,
                'name': info.get('longName') or info.get('shortName'),
                'country': info.get('country'),
                'exchange': info.get('exchange'),
                'currency': info.get('currency'),
                'ipo': info.get('firstTradeDateEpochUtc'),
                'share_outstanding': info.get('sharesOutstanding'),
                'float_shares': info.get('floatShares'),
                'market_cap': info.get('marketCap'),
            }
    except:
        pass
    return None

# Load existing data
print("Loading existing data...")
existing_df = pd.read_csv('all_stocks_raw.csv')
existing_symbols = set(existing_df['symbol'].tolist())
print(f"Existing: {len(existing_symbols)} stocks")

# Load all symbols
all_symbols_df = pd.read_csv('us_stock_symbols.csv')
all_symbols = all_symbols_df['symbol'].tolist()
print(f"Total symbols: {len(all_symbols)}")

# Find missing
missing_symbols = [s for s in all_symbols if s not in existing_symbols]
print(f"Missing: {len(missing_symbols)} stocks\n")

# Check test symbols
test_syms = ['RPGL', 'FTEL', 'MB', 'AEHL']
for sym in test_syms:
    if sym in missing_symbols:
        print(f"✓ {sym} will be fetched")

print(f"\nFetching with 15 threads...\n")

# Fetch in parallel
new_rows = []
completed = 0
errors = 0

with ThreadPoolExecutor(max_workers=15) as executor:
    future_to_symbol = {executor.submit(fetch_stock, symbol): symbol for symbol in missing_symbols}
    
    for future in as_completed(future_to_symbol):
        completed += 1
        result = future.result()
        
        if result:
            new_rows.append(result)
        else:
            errors += 1
        
        if completed % 100 == 0:
            success_rate = len(new_rows) * 100 // completed if completed > 0 else 0
            print(f"Progress: {completed}/{len(missing_symbols)} ({completed*100//len(missing_symbols)}%) | "
                  f"Success: {len(new_rows)} ({success_rate}%) | Errors: {errors}")
            sys.stdout.flush()

print(f"\n✓ Fetched {len(new_rows)} new stocks")

# Combine
new_df = pd.DataFrame(new_rows)
combined_df = pd.concat([existing_df, new_df], ignore_index=True)
combined_df = combined_df.sort_values('symbol').drop_duplicates('symbol')

# Save
combined_df.to_csv('all_stocks_complete.csv', index=False)
print(f"✓ Saved {len(combined_df)} total stocks to all_stocks_complete.csv")

# Summary
print(f"\nSummary:")
print(f"Total stocks: {len(combined_df)}")
print(f"With name: {combined_df['name'].notnull().sum()}")
print(f"With shares outstanding: {combined_df['share_outstanding'].notnull().sum()}")
print(f"With market cap: {combined_df['market_cap'].notnull().sum()}")

# Check if test symbols are there
print(f"\nVerifying test symbols:")
for sym in test_syms:
    if sym in combined_df['symbol'].values:
        row = combined_df[combined_df['symbol'] == sym].iloc[0]
        print(f"✓ {sym}: {row['name']} - Shares: {row['share_outstanding']}")
