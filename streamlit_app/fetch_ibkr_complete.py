#!/usr/bin/env python3
"""
Fetch comprehensive market data from IBKR including:
- Volume, bid/ask, last price
- Shortable shares
- RT Volume (real-time volume with trades/min)
- Historical volatility
"""
import pandas as pd
import os
from dotenv import load_dotenv
from ib_insync import IB, Stock
import time
import math

load_dotenv()

IBKR_HOST = os.getenv('IBKR_HOST', '127.0.0.1')
IBKR_PORT = int(os.getenv('IBKR_PORT', 7497))
IBKR_CLIENT_ID = int(os.getenv('IBKR_CLIENT_ID', 1))

def connect_ibkr():
    """Connect to Interactive Brokers"""
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

def get_complete_data(ib, ticker):
    """Fetch comprehensive market data for a stock"""
    try:
        contract = Stock(ticker, 'SMART', 'USD')
        
        # Qualify contract
        qualified = ib.qualifyContracts(contract)
        if not qualified:
            return None
        contract = qualified[0]
        
        # Request market data with multiple generic ticks:
        # 233 = RTVolume (real-time volume with trades/min)
        # 236 = Shortable shares
        # 104 = Historical volatility
        # 165 = Miscellaneous stats
        generic_ticks = '233,236,104,165'
        
        ib.reqMarketDataType(1)  # Live data
        ticker_obj = ib.reqMktData(contract, generic_ticks, False, False)
        
        # Also request tick-by-tick trade data to count trades
        trade_ticks = []
        
        def on_tick_by_tick(ticker, tick_type, time):
            if tick_type == 'Trade':
                trade_ticks.append(time)
        
        # Subscribe to tick-by-tick trades for 1 minute
        ticker_obj.updateEvent += on_tick_by_tick
        
        # Wait for data (extended to capture trades)
        ib.sleep(3.0)
        
        # Extract standard fields
        data = {
            'symbol': ticker,
            'last_price': ticker_obj.last if ticker_obj.last and not math.isnan(ticker_obj.last) else None,
            'bid': ticker_obj.bid if ticker_obj.bid and not math.isnan(ticker_obj.bid) else None,
            'ask': ticker_obj.ask if ticker_obj.ask and not math.isnan(ticker_obj.ask) else None,
            'volume': ticker_obj.volume if ticker_obj.volume and not math.isnan(ticker_obj.volume) else None,
            'bid_size': ticker_obj.bidSize if ticker_obj.bidSize and not math.isnan(ticker_obj.bidSize) else None,
            'ask_size': ticker_obj.askSize if ticker_obj.askSize and not math.isnan(ticker_obj.askSize) else None,
            'high': ticker_obj.high if ticker_obj.high and not math.isnan(ticker_obj.high) else None,
            'low': ticker_obj.low if ticker_obj.low and not math.isnan(ticker_obj.low) else None,
            'close': ticker_obj.close if ticker_obj.close and not math.isnan(ticker_obj.close) else None,
            'halted': ticker_obj.halted if hasattr(ticker_obj, 'halted') else None
        }
        
        # Calculate trades per minute from collected tick data
        if trade_ticks:
            data['trades_per_minute'] = len(trade_ticks) * 20  # Extrapolate 3s sample to 1 minute
            data['sample_trade_count'] = len(trade_ticks)
        else:
            data['trades_per_minute'] = None
            data['sample_trade_count'] = 0
        
        # Extract RT Volume data (tick 233)
        # Format: price;size;time;totalVolume;VWAP;singleTrade
        if hasattr(ticker_obj, 'rtVolume') and ticker_obj.rtVolume:
            try:
                parts = ticker_obj.rtVolume.split(';')
                if len(parts) >= 6:
                    data['rt_price'] = float(parts[0]) if parts[0] else None
                    data['rt_size'] = int(parts[1]) if parts[1] else None
                    data['rt_time'] = int(parts[2]) if parts[2] else None
                    data['rt_total_volume'] = int(parts[3]) if parts[3] else None
                    data['rt_vwap'] = float(parts[4]) if parts[4] else None
                    data['rt_single_trade'] = parts[5] == 'true' if len(parts) > 5
        # Format: price;size;time;totalVolume;VWAP;singleTrade
        if hasattr(ticker_obj, 'rtVolume') and ticker_obj.rtVolume:
            try:
                parts = ticker_obj.rtVolume.split(';')
                if len(parts) >= 6:
                    data['rt_price'] = float(parts[0]) if parts[0] else None
                    data['rt_size'] = int(parts[1]) if parts[1] else None
                    data['rt_time'] = int(parts[2]) if parts[2] else None
                    data['rt_total_volume'] = int(parts[3]) if parts[3] else None
                    data['rt_vwap'] = float(parts[4]) if parts[4] else None
            except Exception as e:
                print(f"  RT Volume parse error for {ticker}: {e}")
        
        # Extract historical volatility (tick 104)
        if hasattr(ticker_obj, 'histVolatility'):
            hv = ticker_obj.histVolatility
            if hv and not math.isnan(hv):
                data['hist_volatility'] = hv
            else:
                data['hist_volatility'] = None
        else:
            data['hist_volatility'] = None
        
        # Calculate approximate trades per minute from RT Volume
        # (This is an approximation based on volume changes)
        if data.get('volume') and data.get('rt_total_volume'):
            # If we have both daily and RT volume, we can estimate activity
            data['volume_ratio'] = data['volume'] / max(1, data['rt_total_volume'])
        
        # Cancel subscription
        try:
            ib.cancelMktData(contract)
        except:
            pass
        
        return data
        
    except Exception as e:
        print(f"  Error with {ticker}: {e}")
        return None

def fetch_all_stocks(input_csv='all_stocks_complete.csv', output_csv='ibkr_complete_data.csv', 
                     batch_size=100, max_stocks=None):
    """Fetch complete IBKR data for all stocks"""
    
    # Connect to IBKR
    ib = connect_ibkr()
    if not ib:
        return
    
    # Load symbols
    try:
        df = pd.read_csv(input_csv)
        symbols = df['symbol'].dropna().unique().tolist()
        
        if max_stocks:
            symbols = symbols[:max_stocks]
        
        print(f"Loaded {len(symbols)} symbols from {input_csv}")
    except Exception as e:
        print(f"Error loading symbols: {e}")
        ib.disconnect()
        return
    
    results = []
    total = len(symbols)
    start_time = time.time()
    
    print(f"\n{'='*60}")
    print(f"Fetching IBKR data for {total} stocks")
    print(f"Estimated time: ~{(total * 2.5) / 60:.1f} minutes")
    print(f"{'='*60}\n")
    
    for idx, symbol in enumerate(symbols, 1):
        data = get_complete_data(ib, symbol)
        if data:
            results.append(data)
        
        # Progress update
        if idx % 50 == 0 or idx == total:
            elapsed = time.time() - start_time
            rate = idx / elapsed if elapsed > 0 else 0
            remaining = (total - idx) / rate if rate > 0 else 0
            
            success = len(results)
            success_rate = (success / idx * 100) if idx > 0 else 0
            
            print(f"[{idx:,}/{total:,}] {success_rate:.1f}% success | "
                  f"{elapsed/60:.1f}m elapsed | {remaining/60:.1f}m remaining")
        
        # Save periodically
        if idx % batch_size == 0:
            df_results = pd.DataFrame(results)
            df_results.to_csv(output_csv, index=False)
            print(f"  💾 Saved {len(results)} records to {output_csv}")
    
    # Final save
    df_results = pd.DataFrame(results)
    df_results.to_csv(output_csv, index=False)
    
    # Disconnect
    ib.disconnect()
    
    # Summary
    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"✓ Complete!")
    print(f"Total stocks processed: {total:,}")
    print(f"Successfully fetched: {len(results):,}")
    print(f"Success rate: {len(results)/total*100:.1f}%")
    print(f"Time elapsed: {elapsed/60:.1f} minutes")
    print(f"Output: {output_csv}")
    print(f"{'='*60}")
    
    # Show sample of data
    if len(results) > 0:
        print(f"\nSample data (first 5 rows):")
        print(df_results.head())
        print(f"\nColumns: {list(df_results.columns)}")
        print(f"\nData availability:")
        for col in df_results.columns:
            non_null = df_results[col].notna().sum()
            print(f"  {col:20} : {non_null:,} ({non_null/len(df_results)*100:.1f}%)")

if __name__ == '__main__':
    import sys
    
    # Allow command line arguments
    max_stocks = int(sys.argv[1]) if len(sys.argv) > 1 else None
    
    if max_stocks:
        print(f"Testing with first {max_stocks} stocks")
    
    fetch_all_stocks(max_stocks=max_stocks)
