#!/usr/bin/env python3
"""
Benzinga Pro News Scraper
Since the API doesn't return news visible in the Pro dashboard,
this scrapes the actual pro.benzinga.com dashboard you're paying for
"""

import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime

def fetch_benzinga_pro_news(symbols, session_cookies=None):
    """
    Fetch news from Benzinga Pro dashboard
    
    Args:
        symbols: List of stock symbols
        session_cookies: Dict of cookies from your pro.benzinga.com session
    
    Returns:
        Dict mapping symbol to list of news articles
    """
    
    if not session_cookies:
        print("⚠️  Need Benzinga Pro session cookies to scrape dashboard")
        print("\nTo get cookies:")
        print("1. Log into pro.benzinga.com in Chrome")
        print("2. Open DevTools (F12) → Application → Cookies")
        print("3. Copy the session cookie values")
        return {}
    
    news_dict = {symbol: [] for symbol in symbols}
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Referer': 'https://pro.benzinga.com/dashboard'
    }
    
    # Try the news API endpoint that the dashboard uses
    dashboard_api = 'https://pro.benzinga.com/api/v1/news'
    
    for symbol in symbols:
        try:
            params = {'tickers': symbol, 'limit': 20}
            response = requests.get(
                dashboard_api,
                params=params,
                headers=headers,
                cookies=session_cookies,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                news_dict[symbol] = data.get('news', [])
                print(f"  {symbol}: {len(news_dict[symbol])} articles")
            else:
                print(f"  {symbol}: API returned {response.status_code}")
            
            time.sleep(0.2)
            
        except Exception as e:
            print(f"  ⚠️  {symbol}: {e}")
    
    return news_dict


def print_setup_instructions():
    """Print instructions for getting session cookies"""
    print("""
╔════════════════════════════════════════════════════════════════╗
║  Benzinga Pro Dashboard News Scraper Setup                    ║
╚════════════════════════════════════════════════════════════════╝

Since the Benzinga API doesn't return the news you see in the Pro
dashboard, we need to use your session to access it directly.

SETUP STEPS:
1. Open Chrome and go to https://pro.benzinga.com/dashboard
2. Make sure you're logged in (you should see the news feed)
3. Press F12 to open DevTools
4. Go to: Application tab → Storage → Cookies → https://pro.benzinga.com
5. Find these cookies and copy their values:
   - _session
   - XSRF-TOKEN
   - any cookie with 'auth' or 'session' in the name

6. Create a file: benzinga_cookies.json with:
   {
       "_session": "your_session_value_here",
       "XSRF-TOKEN": "your_token_here"
   }

Then this scraper will work!
""")


if __name__ == '__main__':
    import sys
    import os
    
    # Check if cookie file exists
    cookie_file = os.path.join(os.path.dirname(__file__), '..', 'benzinga_cookies.json')
    
    if not os.path.exists(cookie_file):
        print_setup_instructions()
        sys.exit(1)
    
    # Load cookies
    with open(cookie_file, 'r') as f:
        cookies = json.load(f)
    
    # Test with BSLK and DBRG
    test_symbols = ['BSLK', 'DBRG', 'RPGL', 'MASK']
    print(f"\nTesting Benzinga Pro scraper with: {test_symbols}\n")
    
    news_data = fetch_benzinga_pro_news(test_symbols, cookies)
    
    print(f"\n✓ Results:")
    for symbol, articles in news_data.items():
        print(f"{symbol}: {len(articles)} articles")
        if articles:
            print(f"  Latest: {articles[0].get('title', articles[0].get('headline', 'No title'))[:80]}")
