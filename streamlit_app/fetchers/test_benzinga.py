#!/usr/bin/env python3
import argparse, time, sys, requests, re
from collections import defaultdict

NEWS_URL = "https://api.benzinga.com/api/v2/news"
CHAN_URL = "https://api.benzinga.com/api/v2/channels"

def fetch_news(token, since, page, page_size=100, channels=None):
    params = {
        "token": token,
        "updatedSince": str(since),
        "page": str(page),
        "pageSize": str(page_size),
        "sort": "updated:desc",
        # omit displayOutput=full to avoid control-char issues
    }
    if channels:
        params["channels"] = channels
    r = requests.get(NEWS_URL, headers={"accept":"application/json"}, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def fetch_channels(token):
    r = requests.get(CHAN_URL, headers={"accept":"application/json"}, params={"token": token}, timeout=30)
    r.raise_for_status()
    return r.json()

def item_has_ticker(item, ticker):
    ticker = ticker.upper()
    for s in (item.get("stocks") or []):
        if isinstance(s, dict) and (s.get("name","").upper() == ticker):
            return True
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--days", type=int, default=2)
    ap.add_argument("--ticker", default="CRWD")
    ap.add_argument("--needle", default="Recent Short Interest")  # set "" to disable
    ap.add_argument("--max-pages", type=int, default=50)
    ap.add_argument("--page-size", type=int, default=100)
    ap.add_argument("--scan-channels", action="store_true", help="Iterate channels if baseline finds matches")
    args = ap.parse_args()

    since = int(time.time()) - args.days * 86400
    needle_re = re.compile(re.escape(args.needle), re.IGNORECASE) if args.needle else None

    def find_matches(channels=None):
        hits = []
        for p in range(args.max_pages):
            data = fetch_news(args.token, since, p, args.page_size, channels=channels)
            if not data:
                break
            for it in data:
                title = it.get("title","") or ""
                if (args.ticker and item_has_ticker(it, args.ticker)) or (needle_re and needle_re.search(title)):
                    hits.append(it)
        return hits

    # 1) Baseline
    base_hits = find_matches(channels=None)
    print(f"Baseline hits: {len(base_hits)} (no channels filter)")
    for it in base_hits[:25]:
        print(f'{it.get("updated","")} | {it.get("title","")} | {it.get("url","")}')

    if not args.scan_channels:
        return 0

    if not base_hits:
        print("\nNothing found in baseline. Likely not in your API entitlement (even if Pro UI shows it).")
        return 0

    # 2) Iterate channels
    chans = fetch_channels(args.token)
    # expect list of objects with id/name (shape varies by account)
    # We’ll try both id and name if available.
    id_name = []
    for c in chans if isinstance(chans, list) else []:
        cid = str(c.get("id","")).strip()
        name = str(c.get("name","")).strip()
        if cid or name:
            id_name.append((cid, name))

    by_channel = defaultdict(int)
    for cid, name in id_name:
        key = cid or name
        try:
            hits = find_matches(channels=key)
            if hits:
                by_channel[f"{key} ({name})"] = len(hits)
        except Exception:
            # ignore channel failures; some channels may be invalid for news endpoint
            pass

    print("\nChannels producing hits:")
    for k, v in sorted(by_channel.items(), key=lambda x: -x[1]):
        print(f"{v:4d}  {k}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
