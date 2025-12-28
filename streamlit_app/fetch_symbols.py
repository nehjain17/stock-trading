#!/usr/bin/env python3
"""
Fetch symbols from Finnhub, filter by share float/outsanding, and save to Excel/CSV.

Usage:
  python fetch_symbols.py --exchange US --limit 1000 --max-float 20000000 --out symbols.xlsx

Requires: FINNHUB_API_KEY in .env or environment.
"""
import os
import time
import argparse
import requests
import pandas as pd
from dotenv import load_dotenv
import yfinance as yf

load_dotenv()

FINNHUB_KEY = os.getenv('FINNHUB_API_KEY')
ALPHA_KEY = os.getenv('ALPHA_VANTAGE_KEY')


def fetch_exchange_symbols(exchange='US', limit=None):
    url = 'https://finnhub.io/api/v1/stock/symbol'
    params = {'exchange': exchange, 'token': FINNHUB_KEY}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    symbols = [d.get('symbol') for d in data if d.get('symbol')]
    if limit:
        return symbols[:limit]
    return symbols


def get_yahoo_finance_data(symbol):
    """Fetch shares outstanding and other data from Yahoo Finance."""
    result = {
        'share_outstanding': None,
        'float_shares': None,
        'market_cap': None,
        'name': None,
    }
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        if info:
            result['name'] = info.get('longName') or info.get('shortName')
            result['share_outstanding'] = info.get('sharesOutstanding')
            result['float_shares'] = info.get('floatShares')
            result['market_cap'] = info.get('marketCap')
    except Exception:
        pass
    
    return result


def get_share_outstanding(symbol):
    # Collect profile + metric info and return a dict of useful fields
    result = {
        'share_outstanding': None,
        'float_shares': None,
        'market_cap': None,
        'name': None,
        'country': None,
        'currency': None,
        'exchange': None,
        'ipo': None,
    }

    # First, try Yahoo Finance for shares data (free and reliable)
    yf_data = get_yahoo_finance_data(symbol)
    if yf_data['share_outstanding']:
        result['share_outstanding'] = yf_data['share_outstanding']
    if yf_data['float_shares']:
        result['float_shares'] = yf_data['float_shares']
    if yf_data['market_cap']:
        result['market_cap'] = yf_data['market_cap']
    if yf_data['name']:
        result['name'] = yf_data['name']

    # Then get profile data from Finnhub (for exchange, country, etc.)
    try:
        url = 'https://finnhub.io/api/v1/stock/profile2'
        params = {'symbol': symbol, 'token': FINNHUB_KEY}
        resp = requests.get(url, params=params, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        if data:
            if not result['name']:  # Use Finnhub name if Yahoo didn't provide one
                result['name'] = data.get('name')
            result['country'] = data.get('country')
            result['currency'] = data.get('currency')
            result['exchange'] = data.get('exchange')
            result['ipo'] = data.get('ipo')
            # finnhub sometimes provides marketCapitalization
            if data.get('marketCapitalization') and not result['market_cap']:
                try:
                    result['market_cap'] = int(data.get('marketCapitalization'))
                except Exception:
                    pass
    except Exception:
        pass

    return result


def get_alpha_overview(symbol):
    """Fallback to Alpha Vantage OVERVIEW to obtain SharesOutstanding and MarketCapitalization."""
    if not ALPHA_KEY:
        return {}
    try:
        url = 'https://www.alphavantage.co/query'
        params = {'function': 'OVERVIEW', 'symbol': symbol, 'apikey': ALPHA_KEY}
        resp = requests.get(url, params=params, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        out = {}
        if data.get('SharesOutstanding'):
            try:
                out['share_outstanding'] = int(float(data.get('SharesOutstanding')))
            except Exception:
                out['share_outstanding'] = None
        if data.get('MarketCapitalization'):
            try:
                out['market_cap'] = int(float(data.get('MarketCapitalization')))
            except Exception:
                out['market_cap'] = None
        if data.get('Name'):
            out['name'] = data.get('Name')
        return out
    except Exception:
        return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exchange', default='US')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit number of symbols to fetch (default: all)')
    parser.add_argument('--max-float', type=int, default=20000000,
                        help='Maximum float (inclusive) to include')
    parser.add_argument('--out', default='symbols.xlsx')
    parser.add_argument('--exclude-otc', action='store_true', default=True,
                        help='Exclude OTC/pink-sheet listings (based on Finnhub profile exchange)')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    args = parser.parse_args()

    if not FINNHUB_KEY:
        raise SystemExit('FINNHUB_API_KEY not set in environment or .env')

    print(f'Fetching up to {args.limit} symbols from Finnhub exchange={args.exchange}...')
    symbols = fetch_exchange_symbols(args.exchange, limit=args.limit)
    print(f'Got {len(symbols)} symbols; collecting profile/metrics (this may take a while)...')

    rows = []
    skipped_otc = 0
    for i, s in enumerate(symbols, 1):
        try:
            if args.debug:
                print(f'\n--- Processing {s} ---')
            info = get_share_outstanding(s)
            if args.debug:
                print(f'Info: {info}')
            # Optionally exclude OTC/pink-sheet based on profile exchange
            if args.exclude_otc:
                exch = (info.get('exchange') or '').upper() if info else ''
                # Check if exchange contains allowed keywords (more flexible matching)
                allowed_keywords = ['NASDAQ', 'NYSE', 'ARCA', 'AMEX', 'BATS', 'NEW YORK STOCK EXCHANGE']
                is_allowed = any(keyword in exch for keyword in allowed_keywords) if exch else False
                if exch and not is_allowed:
                    skipped_otc += 1
                    if i % 10 == 0 or args.debug:
                        print(f'Processed {i}/{len(symbols)} (skipped OTCs {skipped_otc}) - {s} excluded (exchange: {exch})')
                    time.sleep(0.25)
                    continue
            row = {
                'symbol': s,
                'name': info.get('name'),
                'country': info.get('country'),
                'exchange': info.get('exchange'),
                'currency': info.get('currency'),
                'ipo': info.get('ipo'),
                'share_outstanding': info.get('share_outstanding'),
                'float_shares': info.get('float_shares'),
                'market_cap': info.get('market_cap')
            }
            rows.append(row)
        except Exception as e:
            if args.debug:
                print(f'Error processing {s}: {e}')
            rows.append({'symbol': s, 'name': None, 'country': None, 'exchange': None, 'currency': None,
                         'ipo': None, 'share_outstanding': None, 'float_shares': None, 'market_cap': None})

        if i % 10 == 0:
            print(f'Processed {i}/{len(symbols)}')
        time.sleep(0.1)  # Reduced delay for faster processing

    if args.exclude_otc:
        print(f'Skipped {skipped_otc} OTC/pink-sheet symbols based on profile.exchange')

    df = pd.DataFrame(rows)
    
    # Show some stats
    print(f'\nData Summary:')
    print(f'Total rows: {len(df)}')
    print(f'With name: {df["name"].notnull().sum()}')
    print(f'With share_outstanding: {df["share_outstanding"].notnull().sum()}')
    print(f'With market_cap: {df["market_cap"].notnull().sum()}')
    
    # filtered by max_float where we have a value
    # If no share_outstanding data, filter by market_cap instead (< $500M as proxy for small cap)
    if df['share_outstanding'].notnull().sum() == 0:
        print(f'\nNote: No share_outstanding data available from Finnhub API.')
        print(f'This is common with free/basic API tiers.')
        print(f'Consider using market_cap filter instead or upgrading API plan.')
        df_filtered = df[df['market_cap'].notnull() & (df['market_cap'] <= 500)].copy()
        print(f'Using market_cap <= $500M as alternative filter')
    else:
        df_filtered = df[df['share_outstanding'].notnull() & (df['share_outstanding'] <= args.max_float)].copy()

    # write raw and filtered outputs
    base_out = args.out.rsplit('.', 1)[0]
    raw_csv = base_out + '_raw.csv'
    filtered_csv = base_out + '_filtered.csv'
    df.to_csv(raw_csv, index=False)
    df_filtered.to_csv(filtered_csv, index=False)
    print(f'Wrote raw data to {raw_csv} ({len(df)} rows)')
    print(f'Wrote filtered data to {filtered_csv} ({len(df_filtered)} rows)')

    # attempt Excel write for convenience
    if args.out.lower().endswith('.xlsx'):
        try:
            import openpyxl  # check availability
            with pd.ExcelWriter(args.out, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='raw', index=False)
                df_filtered.to_excel(writer, sheet_name='filtered', index=False)
            print(f'Wrote Excel workbook {args.out}')
        except Exception as e:
            print('Failed to write Excel (openpyxl missing?), fallback CSVs written:', e)


if __name__ == '__main__':
    main()
