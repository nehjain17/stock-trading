#!/usr/bin/env python3
"""
IBKR Scanner with Complete Market Data
Fetches scanner results + enriches with:
- Price data (last, bid, ask, open, high, low, close)
- Volume data (volume, avg volume)
- Shortable shares
- Trade rate (trades/minute)
- Volume rate (volume/minute)
- Borrow fee rate
"""

import argparse
from datetime import datetime, timedelta
from ib_insync import IB, ScannerSubscription, util
import pandas as pd
import os
import time
from dotenv import load_dotenv, find_dotenv
try:
    import yfinance as yf
except Exception:
    yf = None

# Load .env from the project root (walk up if needed)
load_dotenv(find_dotenv(), override=False)

# Scanner codes available
SCANNER_CODES = {
    'top_gainers': 'TOP_PERC_GAIN',
    'top_losers': 'TOP_PERC_LOSE',
    'most_active': 'MOST_ACTIVE',
    'hot_by_volume': 'HOT_BY_VOLUME',
    'top_volume': 'TOP_VOLUME',
    'hot_by_price': 'HOT_BY_PRICE',
    # API does not expose AFTER_HOURS_TOP_PERC_GAIN; alias to TOP_PERC_GAIN
    # and compute after-hours change using last vs prior close
    'after_hours_gainers': 'TOP_PERC_GAIN',
}

def fetch_scanner_with_market_data(scan_type='top_gainers', port=None, max_results=50):
    """Fetch scanner data from IBKR and enrich with market data"""
    
    ib = IB()
    
    # Get port from .env if not specified
    if port is None:
        port = int(os.getenv('IBKR_PORT', 7496))
    
    try:
        # Connect to IBKR
        ib.connect('127.0.0.1', port, clientId=999, readonly=True, timeout=20)
        print(f"✓ Connected to IBKR on port {port}")
        
        # Set market data type based on scan type
        if scan_type == 'after_hours_gainers':
            # For after-hours, use delayed data (3) to ensure after-hours prices are available
            try:
                ib.reqMarketDataType(3)
                print("✓ Market data type set to delayed (for after-hours)")
            except Exception as e:
                print(f"⚠ Failed to set delayed data: {e}")
                # Fallback to frozen
                try:
                    ib.reqMarketDataType(2)
                    print("⚠ Falling back to frozen market data")
                except Exception:
                    print("⚠ Unable to set market data type; continuing")
        else:
            # Normal: real-time (1), fallback to frozen (2), then delayed (3)
            try:
                ib.reqMarketDataType(1)
                print("✓ Market data type set to real-time")
            except Exception:
                try:
                    ib.reqMarketDataType(2)
                    print("⚠ Falling back to frozen market data")
                except Exception:
                    try:
                        ib.reqMarketDataType(3)
                        print("⚠ Falling back to delayed market data")
                    except Exception:
                        print("⚠ Unable to set market data type; continuing")
        
        # Step 1: Get scanner results (with fallbacks for location codes)
        # Prefer major exchanges first for after-hours to avoid OTC/pink sheets
        if scan_type == 'after_hours_gainers':
            location_candidates = [
                'STK.US.MAJOR',
                'STK.US.NASDAQ',
                'STK.US.NYSE',
                'STK.US',
            ]
        else:
            location_candidates = [
                'STK.US.MAJOR',
                'STK.US.NASDAQ',
                'STK.US.NYSE',
                'STK.US',
            ]

        scan_results = []
        def _is_otc(details):
            # Try multiple hints to detect OTC/Pink listings and exclude them
            pe = str(getattr(details.contract, 'primaryExchange', '') or '').upper()
            me = str(getattr(details, 'marketName', '') or '').upper()
            ve = str(getattr(details, 'validExchanges', '') or '').upper()
            candidates = ['OTC', 'OTCM', 'PINK', 'PINKSHEETS']
            if any(x in pe for x in candidates):
                return True
            if any(x in me for x in candidates):
                return True
            if any(x in ve.split(',') for x in candidates):
                return True
            return False

        for loc in location_candidates:
            try:
                # Exclude ultra-low priced symbols to better match TWS "Top % After-Hours Gainers"
                # (many OTC/pink sheet names otherwise dominate when using STK.US)
                min_price = 0.5 if scan_type == 'after_hours_gainers' else None

                scanner = ScannerSubscription(
                    instrument='STK',
                    locationCode=loc,
                    scanCode=SCANNER_CODES.get(scan_type, 'TOP_PERC_GAIN'),
                    numberOfRows=max_results,
                    abovePrice=min_price if min_price is not None else None,
                )
                print(f"Requesting {scan_type} scanner data at location {loc}...")
                scan_results = ib.reqScannerData(scanner)
                # Give the scanner a moment in case data trickles in
                ib.sleep(1.5)
                # Drop OTC/Pink results explicitly if any slipped through
                if len(scan_results) > 0:
                    filtered = [it for it in scan_results if not _is_otc(it.contractDetails)]
                    if len(filtered) != len(scan_results):
                        print(f"  • Filtered out {len(scan_results) - len(filtered)} OTC/Pink symbols")
                    scan_results = filtered
                    print(f"✓ Found {len(scan_results)} stocks at {loc}")
                    break
                else:
                    print(f"⚠ No results at {loc}; trying next location")
            except Exception as e:
                print(f"⚠ Scanner error at {loc}: {e}")

        if len(scan_results) == 0:
            print("✗ Scanner returned 0 results across all locations")
            # Return empty frame early to avoid downstream errors
            return pd.DataFrame()
        
        # Step 2: Request market data in batches for all contracts to avoid rate limits and speed up
        contracts = [item.contractDetails.contract for item in scan_results]
        data = []
        batch_size = 10  # Process in batches of 10 to avoid overwhelming the API
        for batch_start in range(0, len(contracts), batch_size):
            batch_contracts = contracts[batch_start:batch_start + batch_size]
            tickers = [ib.reqMktData(contract, '236,293,294,295,420', False, False) for contract in batch_contracts]
            
            print(f"\nFetching market data for batch {batch_start // batch_size + 1} ({len(tickers)} stocks)...")
            
            start_time = time.time()
            max_wait = 10.0  # Reduced max wait time per batch for speed
            while time.time() - start_time < max_wait:
                all_ready = all(
                    t.last is not None and
                    t.close is not None and
                    t.volume is not None and
                    hasattr(t, 'shortableShares') and t.shortableShares is not None and
                    hasattr(t, 'tradeCount') and t.tradeCount is not None and
                    hasattr(t, 'tradeRate') and t.tradeRate is not None and
                    hasattr(t, 'volumeRate') and t.volumeRate is not None and
                    hasattr(t, 'feeRate') and t.feeRate is not None
                    for t in tickers
                )
                if all_ready:
                    break
                ib.sleep(0.1)  # Faster poll interval
            
            if not all_ready:
                print("⚠ Some data fields may not have populated within the timeout period for this batch.")
            
            # Extract data for this batch
            for j, (item, ticker) in enumerate(zip(scan_results[batch_start:batch_start + batch_size], tickers), batch_start + 1):
                contract = item.contractDetails.contract
                try:
                    row = {
                        'rank': j,
                        'symbol': contract.symbol,
                        'exchange': contract.primaryExchange,
                        
                        # Price data
                        'last_price': ticker.last if ticker.last else None,
                        'bid': ticker.bid if ticker.bid else None,
                        'ask': ticker.ask if ticker.ask else None,
                        'open': ticker.open if ticker.open else None,
                        'high': ticker.high if ticker.high else None,
                        'low': ticker.low if ticker.low else None,
                        'close': ticker.close if ticker.close else None,
                        
                        # Volume data
                        'volume': ticker.volume if ticker.volume else None,
                        'avg_volume': ticker.avVolume if ticker.avVolume else None,
                        
                        # Trading activity metrics
                        'shortable_shares': ticker.shortableShares if hasattr(ticker, 'shortableShares') else None,
                        'trade_count': ticker.tradeCount if hasattr(ticker, 'tradeCount') else None,
                        'trade_rate': ticker.tradeRate if hasattr(ticker, 'tradeRate') else None,
                        'volume_rate': ticker.volumeRate if hasattr(ticker, 'volumeRate') else None,
                        'borrow_fee_rate': abs(ticker.feeRate) if hasattr(ticker, 'feeRate') and ticker.feeRate < 0 else None,
                        
                        # Additional useful fields
                        'bid_size': ticker.bidSize if ticker.bidSize else None,
                        'ask_size': ticker.askSize if ticker.askSize else None,
                        'last_size': ticker.lastSize if ticker.lastSize else None,
                        
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    data.append(row)
                    
                    # Progress indicator
                    if j % 10 == 0:
                        print(f"  Processed {j}/{len(scan_results)} stocks...")
                    
                except Exception as e:
                    print(f"  ⚠ {contract.symbol}: {e}")
                    # Add basic data even if market data fails
                    data.append({
                        'rank': j,
                        'symbol': contract.symbol,
                        'exchange': contract.primaryExchange,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
            
            # Cancel market data for this batch
            for ticker in tickers:
                ib.cancelMktData(ticker.contract)
        
        print(f"✓ Complete! Processed {len(data)} stocks")
        
        ib.disconnect()
        
        # Create dataframe
        df = pd.DataFrame(data)
        
        # Calculate change and change % using available fields
        df['change'] = None
        df['change_pct'] = None
        if 'last_price' in df.columns:
            # Prefer prior close; fallback to open if close missing
            if 'close' in df.columns and df['close'].notna().any():
                df['change'] = df['last_price'] - df['close']
                df['change_pct'] = ((df['last_price'] - df['close']) / df['close'] * 100).where(df['close'] != 0)
            elif 'open' in df.columns and df['open'].notna().any():
                df['change'] = df['last_price'] - df['open']
                df['change_pct'] = ((df['last_price'] - df['open']) / df['open'] * 100).where(df['open'] != 0)

        # Fallback fill for missing price/volume/change via Yahoo Finance if available
        if yf is not None:
            try:
                missing_mask = df['last_price'].isna() | df['volume'].isna() | df['change_pct'].isna()
                symbols_missing = df.loc[missing_mask, 'symbol'].dropna().astype(str).tolist()
                if len(symbols_missing) > 0:
                    print(f"\n⚠ Filling missing price/volume/change for {len(symbols_missing)} symbols via Yahoo Finance")
                    for sym in symbols_missing:
                        try:
                            t = yf.Ticker(sym)
                            hist = t.history(period='2d')
                            if hist is None or len(hist) == 0:
                                continue
                            # Use last available bar for current price/volume
                            last_bar = hist.iloc[-1]
                            prev_close = hist.iloc[-2]['Close'] if len(hist) >= 2 else last_bar['Close']
                            idx = df.index[df['symbol'] == sym]
                            if len(idx) == 0:
                                continue
                            i = idx[0]
                            if pd.isna(df.at[i, 'last_price']):
                                df.at[i, 'last_price'] = float(last_bar['Close']) if 'Close' in last_bar else None
                            if pd.isna(df.at[i, 'open']):
                                df.at[i, 'open'] = float(last_bar['Open']) if 'Open' in last_bar else None
                            if pd.isna(df.at[i, 'volume']):
                                df.at[i, 'volume'] = int(last_bar['Volume']) if 'Volume' in last_bar else None
                            # Use prev_close to compute change% if IBKR close missing
                            if pd.isna(df.at[i, 'close']):
                                df.at[i, 'close'] = float(prev_close) if prev_close is not None else None
                            # Recompute change metrics
                            lp = df.at[i, 'last_price']
                            cl = df.at[i, 'close']
                            if lp is not None and cl is not None and cl != 0:
                                df.at[i, 'change'] = lp - cl
                                df.at[i, 'change_pct'] = (lp - cl) / cl * 100
                            # If volume_rate missing, estimate from last 5 minutes
                            if pd.isna(df.at[i, 'volume_rate']):
                                try:
                                    intraday = t.history(period='1d', interval='1m')
                                    if intraday is not None and len(intraday) > 0:
                                        last5 = intraday.tail(5)
                                        vr = float(last5['Volume'].sum()) / max(1, len(last5))
                                        df.at[i, 'volume_rate'] = vr
                                except Exception:
                                    pass
                        except Exception:
                            continue
            except Exception as e:
                print(f"⚠ Yahoo fallback failed: {e}")
        
        return df
        
    except Exception as e:
        print(f"✗ Error: {e}")
        if ib.isConnected():
            ib.disconnect()
        raise

def main():
    parser = argparse.ArgumentParser(description='Fetch IBKR Scanner Data with Complete Market Data')
    parser.add_argument('--scan-type', default='top_gainers', 
                        choices=list(SCANNER_CODES.keys()),
                        help='Type of scan (default: top_gainers)')
    parser.add_argument('--port', type=int, default=None,
                        help='IBKR port (default: from .env or 7496)')
    parser.add_argument('--limit', type=int, default=50,
                        help='Maximum number of results (default: 50)')
    parser.add_argument('--output', default='output/ibkr_scanner_complete.csv',
                        help='Output CSV file path')
    
    args = parser.parse_args()
    
    # Fetch data
    df = fetch_scanner_with_market_data(
        scan_type=args.scan_type,
        port=args.port,
        max_results=args.limit
    )
    
    # Sort by change_pct descending for gainers
    if 'change_pct' in df.columns:
        df = df.sort_values('change_pct', ascending=False).reset_index(drop=True)
        df['rank'] = range(1, len(df) + 1)
    
    # Create output directory if needed
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    
    # Save to CSV
    df.to_csv(args.output, index=False)
    print(f"\n✓ Saved {len(df)} results to {args.output}")
    
    # Display summary
    friendly = {
        'top_gainers': 'Top % Gainers',
        'after_hours_gainers': 'Top % Gainers',
        'top_losers': 'Top % Losers',
        'most_active': 'Most Active',
        'hot_by_volume': 'Hot by Volume',
        'top_volume': 'Top Volume',
        'hot_by_price': 'Hot by Price',
    }.get(args.scan_type, args.scan_type)
    print(f"\nTop 10 {friendly}:")
    display_cols = ['rank', 'symbol', 'change_pct', 'last_price', 'volume', 'shortable_shares', 'trade_rate', 'volume_rate', 'borrow_fee_rate']
    # Only include columns that exist in the dataframe
    display_cols = [col for col in display_cols if col in df.columns]
    
    if len(display_cols) > 0:
        print(df[display_cols].head(10).to_string(index=False))
    else:
        print(df.head(10).to_string(index=False))
    
    print(f"\n📊 Data Summary:")
    print(f"  Total stocks: {len(df)}")
    if 'last_price' in df.columns:
        print(f"  With price data: {df['last_price'].notna().sum()}")
    if 'shortable_shares' in df.columns:
        print(f"  With shortable shares: {df['shortable_shares'].notna().sum()}")
    if 'trade_rate' in df.columns:
        print(f"  With trade rate: {df['trade_rate'].notna().sum()}")
    if 'volume_rate' in df.columns:
        print(f"  With volume rate: {df['volume_rate'].notna().sum()}")
    if 'change_pct' in df.columns:
        print(f"  With change %: {df['change_pct'].notna().sum()}")
    if 'borrow_fee_rate' in df.columns:
        print(f"  With borrow fee rate: {df['borrow_fee_rate'].notna().sum()}")

if __name__ == '__main__':
    main()