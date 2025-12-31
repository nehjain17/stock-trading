#!/usr/bin/env python3
"""
IBKR Scanner + Market Data Fetcher
Gets scanner results then fetches detailed market data for each stock
"""

import argparse
from datetime import datetime
from ib_insync import IB, ScannerSubscription, Stock
import pandas as pd
import os
import time

SCANNER_CODES = {
    'top_gainers': 'TOP_PERC_GAIN',
    'top_losers': 'TOP_PERC_LOSE',
    'most_active': 'MOST_ACTIVE',
    'hot_by_volume': 'HOT_BY_VOLUME',
}

def fetch_scanner_symbols(ib, scan_type='top_gainers', max_results=50):
    """Get symbols from scanner"""
    scanner = ScannerSubscription(
        instrument='STK',
        locationCode='STK.US',
        scanCode=SCANNER_CODES.get(scan_type, 'TOP_PERC_GAIN'),
        numberOfRows=max_results
    )
    
    print(f"Requesting {scan_type} scanner...")
    scan_results = ib.reqScannerData(scanner)
    
    symbols = []
    for i, item in enumerate(scan_results, 1):
        contract = item.contractDetails.contract
        symbols.append({
            'rank': i,
            'symbol': contract.symbol,
            'exchange': contract.primaryExchange
        })
    
    return symbols

def fetch_market_data(ib, symbol, exchange):
    """Fetch detailed market data for a symbol"""
    try:
        contract = Stock(symbol, 'SMART', 'USD')
        qualified = ib.qualifyContracts(contract)
        
        if not qualified:
            return None
        
        contract = qualified[0]
        
        # Request market data (no snapshot, full subscription)
        ticker = ib.reqMktData(contract, '', False, False)
        ib.sleep(2)  # Wait for data to populate
        
        data = {
            'symbol': symbol,
            'exchange': exchange,
            'last_price': ticker.last if ticker.last else None,
            'close': ticker.close if ticker.close else None,
            'change_pct': ((ticker.last - ticker.close) / ticker.close * 100) if (ticker.last and ticker.close and ticker.close != 0) else None,
            'bid': ticker.bid if ticker.bid else None,
            'ask': ticker.ask if ticker.ask else None,
            'volume': ticker.volume if ticker.volume else None,
            'bid_size': ticker.bidSize if ticker.bidSize else None,
            'ask_size': ticker.askSize if ticker.askSize else None,
            'high': ticker.high if ticker.high else None,
            'low': ticker.low if ticker.low else None,
            'open': ticker.open if ticker.open else None,
        }
        
        ib.cancelMktData(contract)
        return data
        
    except Exception as e:
        print(f"  ✗ {symbol}: {str(e)[:50]}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Fetch IBKR Scanner + Market Data')
    parser.add_argument('--scan-type', default='top_gainers',
                        choices=list(SCANNER_CODES.keys()),
                        help='Type of scan (default: top_gainers)')
    parser.add_argument('--port', type=int, default=7496,
                        help='IBKR port (default: 7496)')
    parser.add_argument('--limit', type=int, default=50,
                        help='Maximum results (default: 50)')
    parser.add_argument('--output', default='../output/ibkr_scanner_data.csv',
                        help='Output CSV file')
    
    args = parser.parse_args()
    
    print("="*70)
    print("IBKR Scanner + Market Data Fetcher")
    print("="*70)
    print(f"\nScan Type: {args.scan_type}")
    print(f"Port: {args.port}")
    print(f"Max Results: {args.limit}\n")
    
    ib = IB()
    
    try:
        # Connect
        ib.connect('127.0.0.1', args.port, clientId=999, readonly=True, timeout=20)
        print(f"✓ Connected to IBKR\n")
        
        # Get scanner results
        symbols = fetch_scanner_symbols(ib, args.scan_type, args.limit)
        print(f"✓ Found {len(symbols)} stocks from scanner\n")
        
        # Fetch market data for each
        print("Fetching market data...")
        results = []
        for item in symbols:
            print(f"  {item['rank']}. {item['symbol']}...", end='')
            data = fetch_market_data(ib, item['symbol'], item['exchange'])
            if data:
                data['rank'] = item['rank']
                data['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                results.append(data)
                print(f" ✓")
            time.sleep(0.3)  # Rate limiting
        
        ib.disconnect()
        
        # Save to CSV
        df = pd.DataFrame(results)
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        df.to_csv(args.output, index=False)
        
        print(f"\n{'='*70}")
        print(f"✓ Complete! Saved {len(df)} results to {args.output}")
        print(f"{'='*70}\n")
        
        # Display top 10
        print("Top 10 with market data:")
        display_cols = ['rank', 'symbol', 'last_price', 'change_pct', 'volume', 'bid', 'ask']
        print(df[display_cols].head(10).to_string(index=False))
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
