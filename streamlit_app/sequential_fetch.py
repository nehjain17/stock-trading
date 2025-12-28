#!/usr/bin/env python3
"""
Sequential fetch of missing stock data with proper rate limiting.
Fetches one stock at a time with delays to avoid rate limits.
Saves progress every 100 stocks so it can be resumed if interrupted.
"""
import pandas as pd
import yfinance as yf
import time
import sys
from datetime import datetime

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
    except Exception as e:
        # Return error info for debugging
        return {'error': str(e), 'symbol': symbol}
    return None

def save_progress(existing_df, new_rows, filename='all_stocks_complete.csv'):
    """Save current progress"""
    if new_rows:
        new_df = pd.DataFrame(new_rows)
        combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        combined_df = combined_df.sort_values('symbol').drop_duplicates('symbol')
        combined_df.to_csv(filename, index=False)
        return combined_df
    return existing_df

# Load existing data
print("Loading existing data from all_stocks_complete.csv...")
existing_df = pd.read_csv('all_stocks_complete.csv')
existing_symbols = set(existing_df['symbol'].tolist())
print(f"Existing: {len(existing_symbols)} stocks")

# Load all symbols
print("Loading all US stock symbols...")
all_symbols_df = pd.read_csv('us_stock_symbols.csv')
all_symbols = all_symbols_df['symbol'].tolist()
print(f"Total symbols: {len(all_symbols)}")

# Find missing
missing_symbols = [s for s in all_symbols if s not in existing_symbols]
print(f"Missing: {len(missing_symbols)} stocks")

# Check test symbols
test_syms = ['RPGL', 'FTEL', 'MB', 'AEHL']
print("\nTest symbols status:")
for sym in test_syms:
    if sym in existing_symbols:
        print(f"  ✓ {sym} - Already have it")
    elif sym in missing_symbols:
        idx = missing_symbols.index(sym)
        print(f"  → {sym} - Will fetch (position {idx+1}/{len(missing_symbols)})")

print(f"\nStarting sequential fetch with 0.5s delay...")
print(f"Estimated time: ~{len(missing_symbols) * 0.5 / 3600:.1f} hours")
print(f"Progress will be saved every 100 stocks\n")

# Fetch sequentially
new_rows = []
successful = 0
errors = 0
start_time = time.time()

for i, symbol in enumerate(missing_symbols, 1):
    result = fetch_stock(symbol)
    
    if result and 'error' not in result:
        new_rows.append(result)
        successful += 1
        status = "✓"
    else:
        errors += 1
        status = "✗"
        if result and 'Rate limit' in result.get('error', ''):
            print(f"\n⚠ Rate limited at {i}/{len(missing_symbols)}. Waiting 60 seconds...")
            time.sleep(60)
    
    # Progress update every 10 stocks
    if i % 10 == 0:
        elapsed = time.time() - start_time
        rate = i / elapsed if elapsed > 0 else 0
        remaining = (len(missing_symbols) - i) / rate / 60 if rate > 0 else 0
        success_rate = successful * 100 // i if i > 0 else 0
        
        print(f"{status} {i}/{len(missing_symbols)} ({i*100//len(missing_symbols)}%) | "
              f"Success: {successful} ({success_rate}%) | Errors: {errors} | "
              f"ETA: {remaining:.0f}m")
        sys.stdout.flush()
    
    # Save progress every 100 stocks
    if i % 100 == 0 and new_rows:
        existing_df = save_progress(existing_df, new_rows)
        print(f"  💾 Saved progress ({len(existing_df)} total stocks)")
        new_rows = []  # Clear after saving
    
    # Delay between requests
    time.sleep(0.5)

# Final save
print(f"\n\nFinal save...")
final_df = save_progress(existing_df, new_rows)

print(f"\n✓ Complete!")
print(f"\nFinal Summary:")
print(f"Total stocks: {len(final_df)}")
print(f"With name: {final_df['name'].notnull().sum()}")
print(f"With shares outstanding: {final_df['share_outstanding'].notnull().sum()}")
print(f"With market cap: {final_df['market_cap'].notnull().sum()}")

# Verify test symbols
print(f"\nVerifying test symbols:")
for sym in test_syms:
    if sym in final_df['symbol'].values:
        row = final_df[final_df['symbol'] == sym].iloc[0]
        shares = row['share_outstanding']
        shares_str = f"{int(shares):,}" if pd.notna(shares) else "N/A"
        print(f"  ✓ {sym}: {row['name']} - Shares: {shares_str}")
    else:
        print(f"  ✗ {sym}: Not found")
