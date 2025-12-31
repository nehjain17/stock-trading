#!/usr/bin/env python3
"""
IBKR Scanner Data Fetcher
Fetches scanner results (top gainers, volume leaders, etc.) from Interactive Brokers
"""

import argparse
from datetime import datetime
from ib_insync import IB, ScannerSubscription
import pandas as pd
import os

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
    """Fetch scanner data from IBKR with all available fields"""
    
    ib = IB()
    
    try:
        # Connect to IBKR
        ib.connect('127.0.0.1', port, clientId=999, readonly=True, timeout=20)
        print(f"✓ Connected to IBKR on port {port}")
        
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
        print(f"Scanner results length: {len(scan_results)}")
        if len(scan_results) == 0:
            print("No scanner results returned. Possible reasons: no market data subscription, wrong scan code/location, or outside market hours.")
        else:
            print("First 3 scanner results:")
            for item in scan_results[:3]:
                print(item)
        # Process results - scanner returns ScanData objects with all metrics
        data = []
        for i, item in enumerate(scan_results, 1):
            contract = item.contractDetails.contract
            details = item.contractDetails
            # Scanner data includes these fields directly
            data.append({
                'rank': item.rank if hasattr(item, 'rank') else i,
                'symbol': contract.symbol,
                'name': details.longName if hasattr(details, 'longName') else '',
                'exchange': contract.primaryExchange,
                'distance': item.distance if hasattr(item, 'distance') else None,  # Often contains %change
                'benchmark': item.benchmark if hasattr(item, 'benchmark') else None,
                'projection': item.projection if hasattr(item, 'projection') else None,
                'legsStr': item.legsStr if hasattr(item, 'legsStr') else None,
                'market_cap_str': details.marketCapitalization if hasattr(details, 'marketCapitalization') else None,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        ib.disconnect()
        return pd.DataFrame(data)
        
    except Exception as e:
        print(f"✗ Error: {e}")
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
