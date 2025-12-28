#!/usr/bin/env python3
"""
Fetch shortable shares data from IBKR for all US stocks.
Synchronous version without asyncio issues.
"""
import pandas as pd
import os
from dotenv import load_dotenv
from ib_insync import IB, Stock
import time
import sys
import math

# Load environment variables
load_dotenv()

# IBKR Connection settings
IBKR_HOST = os.getenv('IBKR_HOST', '127.0.0.1')
IBKR_PORT = int(os.getenv('IBKR_PORT', 7497))
IBKR_CLIENT_ID = int(os.getenv('IBKR_CLIENT_ID', 1))

def connect_ibkr():
    """Connect to Interactive Brokers in read-only mode"""
    try:
        ib = IB()
        ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID, readonly=True)
        time.sleep(0.5)
        print("✓ Connected to IBKR")
        return ib
    except Exception as e:
        print(f"✗ IBKR Connection Error: {e}")
        print("Make sure TWS/IB Gateway is running with API enabled")
        return None

def get_shortable_shares(ib, ticker):
    """Fetch shortable shares for a stock using tick type 236"""
    try:
        contract = Stock(ticker, 'SMART', 'USD')
        
        # Qualify the contract first
        qualified = ib.qualifyContracts(contract)
        if not qualified:
            return None
        contract = qualified[0]
        
        # Request market data with generic tick 236 for shortable shares (tick ID 89)
        # Using live data type (1) - may provide more complete data
        ib.reqMarketDataType(1)  # Live data
        ticker_obj = ib.reqMktData(contract, '236', False, False)  # 236 returns tick ID 89 (shortableShares)
        
        # Wait for data to arrive (may take a moment)
        ib.sleep(2.0)
        
        # Check shortableShares attribute (tick ID 89)
        shortable = ticker_obj.shortableShares
        
        # Handle NaN and None values - keep as -1 to distinguish from 0 shares available
        if shortable is None or (isinstance(shortable, float) and math.isnan(shortable)):
            shortable = -1  # -1 means data not available
        else:
            try:
                shortable = int(shortable)
            except (ValueError, TypeError):
                shortable = -1
        
        # Cancel market data subscription
        try:
            ib.cancelMktData(contract)
        except:
            pass
        
        return {
            'symbol': ticker,
            'shortable_shares': shortable
        }
    except Exception as e:
        print(f"Error with {ticker}: {e}")
        return None

def scan_all_stocks(ib, symbols):
    """Scan all stocks for shortable shares"""
    results = []
    total = len(symbols)
    errors = 0
    no_data = 0
    
    print(f"\nScanning {total} stocks for shortable shares...")
    print("This will take some time (~2 seconds per stock)")
    print("Note: Data may not be available outside market hours\n")
    
    for idx, symbol in enumerate(symbols, 1):
        try:
            data = get_shortable_shares(ib, symbol)
            if data:
                results.append(data)
                
                # Track statistics
                if data['shortable_shares'] == -1:
                    no_data += 1
                
                # Progress update every 10 stocks
                if idx % 10 == 0:
                    available_data = len([r for r in results if r['shortable_shares'] >= 0])
                    print(f"Progress: {idx}/{total} ({idx*100//total}%) | "
                          f"Data available: {available_data} | No data: {no_data}")
                    sys.stdout.flush()
                
                # Save progress every 100 stocks
                if idx % 100 == 0 and results:
                    df = pd.DataFrame(results)
                    df.to_csv('shortable_data_temp.csv', index=False)
                    print(f"  💾 Saved progress")
            else:
                errors += 1
            
        except Exception as e:
            errors += 1
            if idx % 10 == 0:
                print(f"Progress: {idx}/{total} ({idx*100//total}%) | Errors: {errors}")
        
        # Small delay to avoid overwhelming IBKR API
        time.sleep(0.1)
    
    return results

def main():
    # Load symbols
    print("Loading symbols from us_stock_symbols.csv...")
    try:
        symbols_df = pd.read_csv('us_stock_symbols.csv')
        symbols = symbols_df['symbol'].tolist()
        print(f"Found {len(symbols)} symbols")
    except Exception as e:
        print(f"Error loading symbols: {e}")
        return
    
    # Connect to IBKR
    ib = connect_ibkr()
    if not ib:
        return
    
    try:
        # Run the scan
        results = scan_all_stocks(ib, symbols)
        
        if results:
            # Save final results
            df = pd.DataFrame(results)
            df = df.sort_values('shortable_shares', ascending=True)
            df.to_csv('shortable_data.csv', index=False)
            
            print(f"\n✓ Complete!")
            print(f"Total stocks scanned: {len(symbols)}")
            print(f"Stocks with data: {len(results)}")
            print(f"Saved to: shortable_data.csv")
            
            # Summary stats
            low_shortable = df[df['shortable_shares'] < 20000]
            print(f"\nStocks with < 20K shortable shares: {len(low_shortable)}")
            
            # Clean up temp file
            if os.path.exists('shortable_data_temp.csv'):
                os.remove('shortable_data_temp.csv')
        else:
            print("\n✗ No data collected")
    
    finally:
        # Disconnect
        try:
            ib.disconnect()
            print("\n✓ Disconnected from IBKR")
        except:
            pass

if __name__ == '__main__':
    main()
