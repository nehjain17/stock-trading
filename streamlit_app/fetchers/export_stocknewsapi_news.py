#!/usr/bin/env python3
import os
import json
import time
from pathlib import Path
import argparse
import pandas as pd
from dotenv import load_dotenv, find_dotenv

try:
    from fetch_news_stocknewsapi import fetch_stocknews_news
except Exception:
    from .fetch_news_stocknewsapi import fetch_stocknews_news


def main():
    parser = argparse.ArgumentParser(description='Export StockNewsAPI articles for all symbols in CSV to a separate file')
    parser.add_argument('--csv', type=str, default=None,
                        help='Path to scanner CSV (default: streamlit_app/output/ibkr_scanner_complete.csv)')
    parser.add_argument('--items', type=int, default=3,
                        help='Articles per query (trial plans support up to 3)')
    parser.add_argument('--mode', choices=['any', 'include', 'only'], default='any')
    parser.add_argument('--date', type=str, default=None,
                        help='Date filter, e.g., last7days or MMDDYYYY-MMDDYYYY')
    parser.add_argument('--datetimerange', type=str, default=None,
                        help='Datetime range, e.g., 01012025+160000-01022025+090000')
    parser.add_argument('--token', type=str, default=None,
                        help='StockNewsAPI token override')
    parser.add_argument('--out', type=str, default=None,
                        help='Output JSON path (default: streamlit_app/output/stocknewsapi_articles.json)')
    parser.add_argument('--symbols', type=str, default=None,
                        help='Comma-separated list of symbols to query (default: all in CSV)')
    args = parser.parse_args()

    # Load envs: local and project root
    load_dotenv(find_dotenv(), override=False)
    root_env = Path(__file__).resolve().parents[2] / '.env'
    if root_env.exists():
        load_dotenv(dotenv_path=str(root_env), override=False)

    base_dir = Path(__file__).resolve().parents[1]
    csv_path = Path(args.csv) if args.csv else (base_dir / 'output' / 'ibkr_scanner_complete.csv')
    out_path = Path(args.out) if args.out else (base_dir / 'output' / 'stocknewsapi_articles.json')

    if not csv_path.exists():
        raise FileNotFoundError(f'CSV not found: {csv_path}')

    df = pd.read_csv(csv_path)
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(',') if s.strip()]
    else:
        symbols = df['symbol'].dropna().astype(str).tolist()
    print(f'Found {len(symbols)} symbols in {csv_path}')

    # Fetch per-symbol to respect trial limits (items per query)
    all_articles = {}
    for idx, sym in enumerate(symbols, 1):
        try:
            news_map = fetch_stocknews_news(
                [sym],
                mode=args.mode,
                items=max(1, min(args.items, 100)),
                page=1,
                token=args.token or None,
                date=args.date,
                datetimerange=args.datetimerange,
                timeout=7,
            )
            arts = news_map.get(sym, [])
            all_articles[sym] = arts
        except Exception as e:
            print(f'⚠ {sym}: {e}')
            all_articles[sym] = []
        if idx % 10 == 0:
            print(f'  Processed {idx}/{len(symbols)} symbols...')
        time.sleep(0.15)  # small pause to be polite to the API

    # Save JSON
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(all_articles, f, indent=2)

    # Summary
    total = sum(len(v) for v in all_articles.values())
    nonzero = sum(1 for v in all_articles.values() if len(v) > 0)
    print(f'✓ Saved StockNewsAPI articles to {out_path}')
    print(f'  Articles: {total} across {nonzero} symbols')


if __name__ == '__main__':
    main()
