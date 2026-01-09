from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from datetime import datetime, timedelta, timezone
import pandas as pd

app = FastAPI()

# Allow React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent

SCREENER_FILES = {
    "most_active": ("ibkr_scanner_metrics_most_active.csv", "news_most_active_ALL_SYMBOLS.csv"),
    "top_gainers": ("ibkr_scanner_metrics_top_gainers.csv", "news_top_gainers_ALL_SYMBOLS.csv"),
    "top_losers": ("ibkr_scanner_metrics_top_losers.csv", "news_top_losers_ALL_SYMBOLS.csv"),
}

FALLBACK_SCANNER = "ibkr_scanner_metrics.csv"
FALLBACK_NEWS = "news_ALL_SYMBOLS.csv"


def now_utc():
    return datetime.now(timezone.utc)


def pick_existing(name: str) -> Path | None:
    p = BASE_DIR / name
    return p if p.exists() else None


def get_paths(screener: str) -> tuple[Path, Path]:
    scanner_name, news_name = SCREENER_FILES.get(screener, (FALLBACK_SCANNER, FALLBACK_NEWS))
    scanner_path = pick_existing(scanner_name) or (BASE_DIR / FALLBACK_SCANNER)
    news_path = pick_existing(news_name) or (BASE_DIR / FALLBACK_NEWS)
    return scanner_path, news_path


def to_dt_utc(df: pd.DataFrame) -> pd.Series:
    if "time_utc" in df.columns:
        return pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
    if "time" in df.columns:
        return pd.to_datetime(df["time"], utc=True, errors="coerce")
    return pd.to_datetime(pd.NaT)


def safe_val(row, col):
    if col not in row:
        return None
    v = row[col]
    if pd.isna(v):
        return None
    return v


@app.get("/api/screener")
def api_screener(screener: str = "most_active", days: int = 3, search: str = ""):
    scanner_path, news_path = get_paths(screener)

    scanner_df = pd.read_csv(scanner_path)
    if "symbol" not in scanner_df.columns:
        return {"error": f"Scanner CSV missing 'symbol' column: {scanner_path.name}"}
    scanner_df["symbol"] = scanner_df["symbol"].astype(str).str.upper().str.strip()

    news_df = pd.read_csv(news_path)
    if "symbol" not in news_df.columns:
        return {"error": f"News CSV missing 'symbol' column: {news_path.name}"}
    news_df["symbol"] = news_df["symbol"].astype(str).str.upper().str.strip()
    if "headline" not in news_df.columns:
        news_df["headline"] = ""

    news_df["published_at_utc"] = to_dt_utc(news_df)

    cutoff = now_utc() - timedelta(days=days)
    news_recent = news_df[news_df["published_at_utc"] >= cutoff].copy()
    news_recent = news_recent[news_recent["symbol"].isin(scanner_df["symbol"].unique())]

    if search:
        news_recent = news_recent[news_recent["headline"].astype(str).str.contains(search, case=False, na=False)]

    # latest headline per symbol
    news_recent = news_recent.sort_values("published_at_utc", ascending=False)
    latest = news_recent.dropna(subset=["published_at_utc"]).drop_duplicates(subset=["symbol"], keep="first")
    latest = latest[["symbol", "headline", "published_at_utc"]].rename(
        columns={"headline": "latest_headline", "published_at_utc": "latest_news_time_utc"}
    )

    counts = news_recent.groupby("symbol", as_index=False).size().rename(columns={"size": "news_count"})
    merged = scanner_df.merge(counts, on="symbol", how="left").merge(latest, on="symbol", how="left")
    merged["news_count"] = merged["news_count"].fillna(0).astype(int)

    rows = []
    for _, r in merged.iterrows():
        latest_dt = r.get("latest_news_time_utc")
        latest_str = None
        if pd.notna(latest_dt):
            latest_str = pd.to_datetime(latest_dt, utc=True).strftime("%Y-%m-%d %H:%M:%S")

        rows.append({
            "symbol": r["symbol"],
            "description": safe_val(r, "description") or "",
            "last": safe_val(r, "last"),
            "pctChange": safe_val(r, "pct_change"),
            "shortableShares": safe_val(r, "shortable_shares"),
            "marketCap": safe_val(r, "market_cap"),
            "floatShares": safe_val(r, "float_shares"),
            "tradesPerMin": safe_val(r, "trade_rate"),
            "volumePerMin": safe_val(r, "effective_volume_per_min") or safe_val(r, "computed_volume_per_min"),
            "volume": safe_val(r, "volume"),
            "latestNewsUtc": latest_str,
            "latestHeadline": safe_val(r, "latest_headline"),
            "newsCount": int(r["news_count"]),
        })

    providers = int(news_recent["provider"].nunique()) if "provider" in news_recent.columns else 0
    symbols = int(scanner_df["symbol"].nunique())
    news_rows = int(len(news_recent))
    symbols_with_news = int((merged["news_count"] > 0).sum())

    label_map = {"all": "All (Merged)", "most_active": "Most Active", "top_gainers": "Top % Gainers", "top_losers": "Top % Losers"}

    return {
        "screener": screener,
        "screenerLabel": label_map.get(screener, screener),
        "days": days,
        "symbols": symbols,
        "newsRows": news_rows,
        "symbolsWithNews": symbols_with_news,
        "providers": providers,
        "rows": rows,
    }


@app.get("/api/headlines")
def api_headlines(screener: str = "most_active", days: int = 3, symbol: str = "", search: str = ""):
    _scanner_path, news_path = get_paths(screener)

    news_df = pd.read_csv(news_path)
    if "symbol" not in news_df.columns:
        return {"symbol": symbol, "days": days, "items": []}
    news_df["symbol"] = news_df["symbol"].astype(str).str.upper().str.strip()
    if "headline" not in news_df.columns:
        news_df["headline"] = ""

    news_df["published_at_utc"] = to_dt_utc(news_df)

    cutoff = now_utc() - timedelta(days=days)
    df = news_df[(news_df["published_at_utc"] >= cutoff) & (news_df["symbol"] == symbol.upper().strip())].copy()

    if search:
        df = df[df["headline"].astype(str).str.contains(search, case=False, na=False)]

    df = df.sort_values("published_at_utc", ascending=False)

    items = []
    for _, r in df.iterrows():
        published = r["published_at_utc"]
        items.append({
            "symbol": r["symbol"],
            "publishedUtc": published.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(published) else "",
            "provider": r.get("provider", "") if pd.notna(r.get("provider", "")) else "",
            "providerName": r.get("provider_name", "") if pd.notna(r.get("provider_name", "")) else "",
            "headline": r.get("headline", "") if pd.notna(r.get("headline", "")) else "",
            "articleId": r.get("articleId", None),
        })

    return {"symbol": symbol.upper().strip(), "days": days, "items": items}
