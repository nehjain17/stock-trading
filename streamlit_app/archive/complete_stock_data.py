#!/usr/bin/env python3
"""
Complete the stock data by fetching missing symbols.
"""
import pandas as pd
import yfinance as yf
import time
import sys

# Load existing data
print("Loading existing data from all_stocks_raw.csv...")
existing_df = pd.read_csv('all_stocks_raw.csv')
existing_symbols = set(existing_df['symbol'].tolist())
print(f"Found {len(existing_symbols)} existing stocks")

# Load all symbols
print("Loading all US stock symbols...")
all_symbols_df = pd.read_csv('us_stock_symbols.csv')
all_symbols = set(all_symbols_df['symbol'].tolist())
print(f"Found {len(all_symbols)} total symbols")

# Find missing
missing_symbols = sorted(all_symbols - existing_symbols)
print(f"\nNeed to fetch {len(missing_symbols)} missing stocks")
print(f"Estimated time: ~{len(missing_symbols) * 0.3 / 60:.0f} minutes\n")

# Check if specific symbols are in missing list
test_syms = ['RPGL', 'FTEL', 'MB', 'AEHL']
for sym in test_syms:
    if sym in missing_symbols:
        print(f"✓ {sym} will be fetched")

print("\nFetching missing stocks...\n")

# Fetch missing stocks
new_rows = []
for i, symbol in enumerate(missing_symbols, 1):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        if info:
            new_rows.append({
                'symbol': symbol,
                'name': info.get('longName') or info.get('shortName'),
                'country': info.get('country'),
                'exchange': info.get('exchange'),
                'currency': info.get('currency'),
                'ipo': info.get('firstTradeDateEpochUtc'),
                'share_outstanding': info.get('sharesOutstanding'),
                'float_shares': info.get('floatShares'),
                'market_cap': info.get('marketCap'),
            })
        
        if i % 50 == 0:
            print(f"Processed {i}/{len(missing_symbols)} ({i*100//len(missing_symbols)}%) - Total new: {len(new_rows)}")
            sys.stdout.flush()
        
        time.sleep(0.3)
        
    except Exception as e:
        if i % 50 == 0:
            print(f"Processed {i}/{len(missing_symbols)} ({i*100//len(missing_symbols)}%) - Errors encountered")
            sys.stdout.flush()
        time.sleep(0.3)

print(f"\n\nFetched {len(new_rows)} new stocks")

# Combine with existing
new_df = pd.DataFrame(new_rows)
combined_df = pd.concat([existing_df, new_df], ignore_index=True)
combined_df = combined_df.sort_values('symbol').drop_duplicates('symbol')

# Save
combined_df.to_csv('all_stocks_complete.csv', index=False)
print(f"\nSaved {len(combined_df)} total stocks to all_stocks_complete.csv")

# Summary
print(f"\nSummary:")
print(f"Total stocks: {len(combined_df)}")
print(f"With name: {combined_df['name'].notnull().sum()}")
print(f"With shares outstanding: {combined_df['share_outstanding'].notnull().sum()}")
print(f"With market cap: {combined_df['market_cap'].notnull().sum()}")
