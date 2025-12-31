#!/usr/bin/env python3
"""
IBKR Scanner Data Fetcher
Fetches scanner results (top gainers, volume leaders, etc.) from Interactive Brokers with enriched market data
"""

import argparse
from datetime import datetime, timedelta
from ib_insync import IB, ScannerSubscription
import pandas as pd
import os
import time

# Scanner codes available
SCANNER_CODES = {
    'top_gainers': 'TOP_PERC_GAIN',
    'top_losers': 'TOP_PERC_LOSE',
    'most_active': 'MOST_ACTIVE',
    'hot_by_volume': 'HOT_BY_VOLUME',
    'top_volume': 'TOP_VOLUME',
    'hot_by_price': 'HOT_BY_PRICE',
}

def fetch_scanner_data(scan_type='top_gainers', port=7496, max_results=50):
    """Fetch scanner data from IBKR with enriched market data including shortable shares and trade rate"""
    
    ib = IB()
    
    try:
        # Connect to IBKR
        ib.connect('127.0.0.1', port, clientId=999, readonly=True, timeout=20)
        print(f"✓ Connected to IBKR on port {port}")
        
        # Set to real-time data (1); fallback to delayed (3) if needed
        ib.reqMarketDataType(1)
        
        # Create scanner subscription
        scanner = ScannerSubscription(
            instrument='STK',
            locationCode='STK.US',
            scanCode=SCANNER_CODES.get(scan_type, 'TOP_PERC_GAIN'),
            numberOfRows=max_results
        )
        
        # Request scanner data
        print(f"Requesting {scan_type} data...")
        scan_results = ib.reqScannerData(scanner)
        
        # Process results in batches for efficiency
        data = []
        batch_size = 10
        for batch_start in range(0, len(scan_results), batch_size):
            batch_results = scan_results[batch_start:batch_start + batch_size]
            tickers = []
            for item in batch_results:
                contract = item.contractDetails.contract
                ticker = ib.reqMktData(contract, '236,293,294,295', False, False)  # 236=shortable, 293=trade count, 294=trade rate, 295=volume rate
                tickers.append(ticker)
            
            # Wait for data to stream in
            start_time = time.time()
            while time.time() - start_time < 10.0:  # Wait up to 10s per batch
                if all(hasattr(t, 'shortableShares') and t.shortableShares is not None and hasattr(t, 'tradeRate') and t.tradeRate is not None for t in tickers):
                    break
                time.sleep(0.2)
            
            # Extract data
            for i, (item, ticker) in enumerate(zip(batch_results, tickers), batch_start + 1):
                contract = item.contractDetails.contract
                details = item.contractDetails
                
                row = {
                    'rank': item.rank if hasattr(item, 'rank') else i,
                    'symbol': contract.symbol,
                    'name': details.longName if hasattr(details, 'longName') else '',
                    'exchange': contract.primaryExchange,
                    'change_pct': item.distance if hasattr(item, 'distance') else None,  # % change for gainers/losers
                    'last_price': ticker.last if ticker.last is not None else None,
                    'volume': ticker.volume if ticker.volume is not None else None,
                    'shortable_shares': ticker.shortableShares if hasattr(ticker, 'shortableShares') else None,
                    'trade_rate': ticker.tradeRate if hasattr(ticker, 'tradeRate') else None,
                    'volume_rate': ticker.volumeRate if hasattr(ticker, 'volumeRate') else None,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                data.append(row)
            
            # Cancel subscriptions for batch
            for ticker in tickers:
                ib.cancelMktData(ticker.contract)
        
        ib.disconnect()
        
        df = pd.DataFrame(data)
        
        # Sort by change_pct descending for gainers/losers
        if scan_type in ['top_gainers', 'top_losers']:
            df = df.sort_values('change_pct', ascending=(scan_type == 'top_losers')).reset_index(drop=True)
            df['rank'] = range(1, len(df) + 1)
        
        return df
        
    except Exception as e:
        print(f"✗ Error: {e}")
        if ib.isConnected():
            ib.disconnect()
        raise

def main():
    parser = argparse.ArgumentParser(description='Fetch IBKR Scanner Data')
    parser.add_argument('--scan-type', default='top_gainers', 
                        choices=list(SCANNER_CODES.keys()),
                        help='Type of scan (default: top_gainers)')
    parser.add_argument('--port', type=int, default=7496,
                        help='IBKR port (default: 7496)')
    parser.add_argument('--limit', type=int, default=50,
                        help='Maximum results (default: 50)')
    parser.add_argument('--output', default='../output/ibkr_scanner.csv',
                        help='Output CSV file')
    
    args = parser.parse_args()
    
    print("="*70)
    print("IBKR Scanner Data Fetcher")
    print("="*70)
    print(f"\nScan Type: {args.scan_type}")
    print(f"Port: {args.port}")
    print(f"Max Results: {args.limit}")
    print(f"Output: {args.output}\n")
    
    # Fetch data
    df = fetch_scanner_data(args.scan_type, args.port, args.limit)
    
    # Save to CSV
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    df.to_csv(args.output, index=False)
    
    print(f"\n{'='*70}")
    print(f"✓ Complete! Saved {len(df)} results to {args.output}")
    print(f"{'='*70}")
    
    # Display top 10
    print(f"\nTop 10 {args.scan_type}:")
    print(df.head(10).to_string(index=False))

if __name__ == '__main__':
    main()