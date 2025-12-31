#!/usr/bin/env python3
import os
import json
from pathlib import Path
import argparse
import pandas as pd
from dotenv import load_dotenv, find_dotenv

try:
    from fetch_news_stocknewsapi import fetch_stocknews_news
except Exception:
    from .fetch_news_stocknewsapi import fetch_stocknews_news

def parse_source(s: str):
    parts = {k: 0 for k in ['B', 'PR', 'S', 'F']}
    for token in str(s).split():
        if ':' in token:
            k, v = token.split(':', 1)
            if k in parts:
                try:
                    parts[k] = int(''.join(ch for ch in v if ch.isdigit()))
                except Exception:
                    parts[k] = 0
    return parts

def is_recent_article(a) -> bool:
    """Return True if article date is today or yesterday.
    Checks fields: created, date, published_date, time.
    """
    try:
        import pandas as pd
        from datetime import datetime, timedelta
        created = (
            a.get('created')
            or a.get('date')
            or a.get('published_date')
            or a.get('time')
            or ''
        )
        if not created:
            return False
        dt = pd.to_datetime(created, utc=True, errors='coerce')
        if dt is None or str(dt) == 'NaT':
            return False
        d = dt.date()
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        return d == today or d == yesterday
    except Exception:
        return False

def main():
    parser = argparse.ArgumentParser(description='Update CSV with StockNewsAPI news without IBKR scan')
    parser.add_argument('--mode', choices=['any', 'include', 'only'], default='any')
    parser.add_argument('--items', type=int, default=50)
    parser.add_argument('--page', type=int, default=1)
    parser.add_argument('--date', type=str, default=None,
                        help='e.g., last7days, last30days, or MMDDYYYY-MMDDYYYY')
    parser.add_argument('--datetimerange', type=str, default=None,
                        help='e.g., 01012025+160000-01022025+090000')
    parser.add_argument('--token', type=str, default=None)
    parser.add_argument('--recent-only', action='store_true', default=False,
                        help='When set, only include articles from today or yesterday')
    parser.add_argument('--symbols', type=str, default=None,
                        help='Comma-separated list of symbols to update (default: all in CSV)')
    args = parser.parse_args()

    # Load env from project root
    load_dotenv(find_dotenv(), override=False)
    root_env = Path(__file__).resolve().parents[2] / '.env'
    if root_env.exists():
        load_dotenv(dotenv_path=str(root_env), override=False)

    base_dir = Path(__file__).resolve().parents[1]
    csv_path = base_dir / 'output' / 'ibkr_scanner_complete.csv'
    articles_json_path = base_dir / 'output' / 'news_articles.json'

    if not csv_path.exists():
        raise FileNotFoundError(f'CSV not found: {csv_path}')

    df = pd.read_csv(csv_path)
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(',') if s.strip()]
    else:
        symbols = df['symbol'].dropna().astype(str).tolist()

    # Fetch news
    news_map = fetch_stocknews_news(
        symbols,
        mode=args.mode,
        items=args.items,
        page=args.page,
        token=args.token or None,
        date=args.date,
        datetimerange=args.datetimerange,
    )

    # Load existing articles JSON
    existing_news = {}
    if articles_json_path.exists():
        try:
            with open(articles_json_path, 'r') as f:
                existing_news = json.load(f)
        except Exception:
            existing_news = {}

    # Update df
    df_updated = df.copy()
    for i, row in df_updated.iterrows():
        sym = str(row.get('symbol', '')).upper()
        if not sym:
            continue
        if args.symbols and sym not in symbols:
            # Skip rows not in filter
            continue
        # Filter to only recent (today or yesterday)
        articles_all = news_map.get(sym, [])
        articles = [a for a in articles_all if is_recent_article(a)] if args.recent_only else articles_all
        s_count = len(articles)
        src = parse_source(row.get('news_source', 'B:0 PR:0 S:0 F:0'))
        src['S'] = s_count
        total = src['B'] + src['PR'] + src['S'] + src['F']
        df_updated.at[i, 'news_count'] = total
        df_updated.at[i, 'news_source'] = f"B:{src['B']} PR:{src['PR']} S:{src['S']} F:{src['F']}"
        if s_count > 0:
            df_updated.at[i, 'latest_news'] = articles[0].get('title', 'No news')
            existing_list = existing_news.get(sym, [])
            merged = articles + existing_list
            seen = set()
            uniq = []
            for a in merged:
                key = (a.get('title', ''), a.get('url', ''))
                if key in seen:
                    continue
                seen.add(key)
                uniq.append(a)
            existing_news[sym] = uniq

    # Save
    df_updated.to_csv(csv_path, index=False)
    with open(articles_json_path, 'w') as f:
        json.dump(existing_news, f, indent=2)

    print('✓ Updated CSV and news_articles.json')

if __name__ == '__main__':
    main()
