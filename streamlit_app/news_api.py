#!/usr/bin/env python3
"""
News API - Pull interface for scanners to query cached news
Provides fast access to pre-fetched news from background monitor
"""
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional

DB_PATH = 'news_cache.db'

def get_news_for_symbols(symbols: List[str], hours: int = 24) -> Dict[str, List[Dict]]:
    """
    Get cached news for specific symbols
    
    Args:
        symbols: List of stock symbols
        hours: How far back to look (default 24 hours)
    
    Returns:
        Dict mapping symbol -> list of news items
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    since = datetime.now() - timedelta(hours=hours)
    
    # Query for multiple symbols
    placeholders = ','.join('?' * len(symbols))
    query = f'''
        SELECT symbol, headline, summary, source, url, published_at, sentiment, is_catalyst
        FROM news
        WHERE symbol IN ({placeholders}) AND published_at >= ?
        ORDER BY published_at DESC
    '''
    
    cursor.execute(query, (*symbols, since.isoformat()))
    results = cursor.fetchall()
    conn.close()
    
    # Group by symbol
    news_by_symbol = {symbol: [] for symbol in symbols}
    
    for row in results:
        symbol = row[0]
        news_by_symbol[symbol].append({
            'headline': row[1],
            'summary': row[2],
            'source': row[3],
            'url': row[4],
            'published_at': row[5],
            'sentiment': row[6],
            'is_catalyst': bool(row[7])
        })
    
    return news_by_symbol

def get_catalyst_stocks(hours: int = 24, min_news: int = 2) -> List[Dict]:
    """
    Get stocks with catalyst news
    
    Args:
        hours: Look back period
        min_news: Minimum catalyst news items
    
    Returns:
        List of stocks with catalyst activity
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    since = datetime.now() - timedelta(hours=hours)
    
    query = '''
        SELECT symbol, COUNT(*) as catalyst_count,
               GROUP_CONCAT(headline, ' | ') as headlines
        FROM news
        WHERE is_catalyst = 1 AND published_at >= ?
        GROUP BY symbol
        HAVING catalyst_count >= ?
        ORDER BY catalyst_count DESC
    '''
    
    cursor.execute(query, (since.isoformat(), min_news))
    results = cursor.fetchall()
    conn.close()
    
    return [
        {
            'symbol': row[0],
            'catalyst_count': row[1],
            'headlines': row[2].split(' | ')
        }
        for row in results
    ]

def get_latest_news(limit: int = 50, catalysts_only: bool = False) -> List[Dict]:
    """
    Get latest news across all stocks
    
    Args:
        limit: Max number of items
        catalysts_only: Only return catalyst news
    
    Returns:
        List of news items
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = '''
        SELECT symbol, headline, summary, source, url, published_at, sentiment, is_catalyst
        FROM news
        WHERE 1=1
    '''
    
    if catalysts_only:
        query += ' AND is_catalyst = 1'
    
    query += ' ORDER BY published_at DESC LIMIT ?'
    
    cursor.execute(query, (limit,))
    results = cursor.fetchall()
    conn.close()
    
    return [
        {
            'symbol': row[0],
            'headline': row[1],
            'summary': row[2],
            'source': row[3],
            'url': row[4],
            'published_at': row[5],
            'sentiment': row[6],
            'is_catalyst': bool(row[7])
        }
        for row in results
    ]

def get_news_count_by_source() -> Dict[str, int]:
    """Get news count by source for monitoring"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT source, COUNT(*) as count
        FROM news
        WHERE published_at >= datetime('now', '-24 hours')
        GROUP BY source
    ''')
    
    results = cursor.fetchall()
    conn.close()
    
    return {row[0]: row[1] for row in results}

def search_news(keyword: str, hours: int = 168, limit: int = 100) -> List[Dict]:
    """
    Search news by keyword
    
    Args:
        keyword: Search term
        hours: Look back period (default 1 week)
        limit: Max results
    
    Returns:
        List of matching news items
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    since = datetime.now() - timedelta(hours=hours)
    
    query = '''
        SELECT symbol, headline, summary, source, url, published_at, sentiment, is_catalyst
        FROM news
        WHERE (headline LIKE ? OR summary LIKE ?) AND published_at >= ?
        ORDER BY published_at DESC
        LIMIT ?
    '''
    
    search_term = f'%{keyword}%'
    cursor.execute(query, (search_term, search_term, since.isoformat(), limit))
    results = cursor.fetchall()
    conn.close()
    
    return [
        {
            'symbol': row[0],
            'headline': row[1],
            'summary': row[2],
            'source': row[3],
            'url': row[4],
            'published_at': row[5],
            'sentiment': row[6],
            'is_catalyst': bool(row[7])
        }
        for row in results
    ]

# Convenience functions for common queries

def get_breaking_news(minutes: int = 30) -> List[Dict]:
    """Get very recent news (last N minutes)"""
    hours = minutes / 60
    return get_latest_news(limit=20)

def get_most_active_symbols(hours: int = 24, limit: int = 20) -> List[Dict]:
    """Get symbols with most news activity"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    since = datetime.now() - timedelta(hours=hours)
    
    query = '''
        SELECT symbol, COUNT(*) as news_count,
               SUM(CASE WHEN is_catalyst = 1 THEN 1 ELSE 0 END) as catalyst_count
        FROM news
        WHERE published_at >= ?
        GROUP BY symbol
        ORDER BY news_count DESC
        LIMIT ?
    '''
    
    cursor.execute(query, (since.isoformat(), limit))
    results = cursor.fetchall()
    conn.close()
    
    return [
        {
            'symbol': row[0],
            'news_count': row[1],
            'catalyst_count': row[2]
        }
        for row in results
    ]


if __name__ == '__main__':
    # Example usage
    print("News API Examples\n")
    
    # Get news for specific symbols
    news = get_news_for_symbols(['AAPL', 'TSLA', 'NVDA'], hours=24)
    for symbol, items in news.items():
        print(f"{symbol}: {len(items)} news items")
    
    # Get catalyst stocks
    print("\nStocks with catalysts:")
    catalysts = get_catalyst_stocks(hours=24, min_news=1)
    for item in catalysts[:5]:
        print(f"  {item['symbol']}: {item['catalyst_count']} catalysts")
    
    # Get latest breaking news
    print("\nLatest news:")
    latest = get_latest_news(limit=5)
    for item in latest:
        print(f"  {item['symbol']}: {item['headline'][:60]}...")
    
    # Source stats
    print("\nNews by source (24h):")
    sources = get_news_count_by_source()
    for source, count in sources.items():
        print(f"  {source}: {count} items")
