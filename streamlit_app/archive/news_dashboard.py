#!/usr/bin/env python3
"""
IBKR Scanner + News Dashboard (Minimal header, browser scroll only)

Fixes KeyError: 0 by using an explicit list for selectbox and mapping safely.
"""

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Tuple, List

import pandas as pd
import streamlit as st

SCRIPT_DIR = Path(__file__).resolve().parent


# ----------------------------
# Path utilities
# ----------------------------
def resolve_path(p: str) -> Path:
    raw = (p or "").strip()
    if not raw:
        return Path(raw)
    path = Path(raw)
    return path if path.is_absolute() else (SCRIPT_DIR / path).resolve()


def pick_existing(primary: Path, fallback: Path) -> Path:
    return primary if primary.exists() else fallback


# ----------------------------
# CLI args
# ----------------------------
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--days", type=int, default=2)
    args, _unknown = p.parse_known_args()
    return args


# ----------------------------
# Data helpers
# ----------------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_float(x) -> Optional[float]:
    try:
        if pd.isna(x):
            return None
        if isinstance(x, str) and x.strip().upper() in {"N/A", ""}:
            return None
        return float(x)
    except Exception:
        return None


def fmt_money(v) -> str:
    v = _to_float(v)
    if v is None:
        return "N/A"
    if v >= 1e12:
        return f"${v/1e12:.2f}T"
    if v >= 1e9:
        return f"${v/1e9:.2f}B"
    if v >= 1e6:
        return f"${v/1e6:.2f}M"
    return f"${v:,.0f}"


def fmt_num(v) -> str:
    v = _to_float(v)
    if v is None:
        return "N/A"
    if v >= 1e9:
        return f"{v/1e9:.2f}B"
    if v >= 1e6:
        return f"{v/1e6:.2f}M"
    if v >= 1e3:
        return f"{v/1e3:.2f}K"
    return f"{v:.2f}" if v < 10 else f"{v:.0f}"


@st.cache_data(ttl=30)
def load_scanner(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "symbol" in df.columns:
        df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    return df


@st.cache_data(ttl=30)
def load_news(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "symbol" in df.columns:
        df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    if "provider" in df.columns:
        df["provider"] = df["provider"].astype(str).str.strip()
    if "provider_name" in df.columns:
        df["provider_name"] = df["provider_name"].astype(str).str.strip()

    if "time_utc" in df.columns:
        df["published_at_utc"] = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
    elif "time" in df.columns:
        df["published_at_utc"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    else:
        df["published_at_utc"] = pd.NaT

    if "headline" not in df.columns:
        df["headline"] = ""

    return df


def filter_news_last_days(news_df: pd.DataFrame, days: int) -> pd.DataFrame:
    if news_df.empty:
        return news_df
    cutoff = now_utc() - timedelta(days=days)
    return news_df[news_df["published_at_utc"] >= cutoff].copy()


def build_symbol_summary(scanner_df: pd.DataFrame, news_df: pd.DataFrame) -> pd.DataFrame:
    if scanner_df.empty:
        return pd.DataFrame()

    if news_df.empty:
        agg = pd.DataFrame({"symbol": scanner_df["symbol"].unique()})
        agg["news_count"] = 0
        agg["latest_headline"] = ""
        agg["latest_news_time_utc"] = pd.NaT
    else:
        tmp = news_df.sort_values("published_at_utc", ascending=False).copy()
        latest = tmp.dropna(subset=["published_at_utc"]).drop_duplicates(subset=["symbol"], keep="first")
        latest = latest[["symbol", "headline", "published_at_utc"]].rename(columns={
            "headline": "latest_headline",
            "published_at_utc": "latest_news_time_utc",
        })
        counts = tmp.groupby("symbol", as_index=False).size().rename(columns={"size": "news_count"})
        agg = counts.merge(latest, on="symbol", how="left")

    out = scanner_df.merge(agg, on="symbol", how="left")
    out["news_count"] = out["news_count"].fillna(0).astype(int)
    return out


# ----------------------------
# Screener config
# ----------------------------
SCREENER_MAP: Dict[str, str] = {
    "Most Active": "most_active",
    "Top % Gainers": "top_gainers",
    "Top % Losers": "top_losers",
}

SCREENER_LABELS: List[str] = list(SCREENER_MAP.keys())


def screener_files(screener_slug: str) -> Tuple[Path, Path]:
    preferred_scanner = resolve_path(f"ibkr_scanner_metrics_{screener_slug}.csv")
    preferred_news = resolve_path(f"news_{screener_slug}_ALL_SYMBOLS.csv")

    fallback_scanner = resolve_path("ibkr_scanner_metrics.csv")
    fallback_news = resolve_path("news_ALL_SYMBOLS.csv")

    scanner_path = pick_existing(preferred_scanner, fallback_scanner)
    news_path = pick_existing(preferred_news, fallback_news)
    return scanner_path, news_path


# ----------------------------
# UI
# ----------------------------
args = _parse_args()
st.set_page_config(page_title="IBKR", page_icon="📰", layout="wide")

st.markdown(
    """
    <style>
      section[data-testid="stSidebar"] { width: 200px !important; }
      .block-container {
        padding-top: 0.4rem;
        padding-bottom: 0.4rem;
        padding-left: 0.6rem;
        padding-right: 0.6rem;
        max-width: 100%;
      }
      #MainMenu {visibility: hidden;}
      footer {visibility: hidden;}
      header {visibility: hidden;}
    </style>
    """,
    unsafe_allow_html=True,
)

# Sidebar (FIXED)
with st.sidebar:
    st.markdown("### Screeners")

    # selectbox returns a LABEL string from SCREENER_LABELS (never 0)
    screener_label = st.selectbox(
        "Screener",
        options=SCREENER_LABELS,
        index=0,
        key="screener_label",
    )
    screener_slug = SCREENER_MAP.get(screener_label, "most_active")

    days = st.number_input("Days", min_value=1, max_value=30, value=int(args.days), step=1, key="days")
    headline_search = st.text_input("Search", value="", placeholder="headline contains...", key="search").strip()
    refresh = st.button("Refresh", key="refresh")

if refresh:
    st.cache_data.clear()
    st.rerun()

scanner_path, news_path = screener_files(screener_slug)

# Load
try:
    scanner_df = load_scanner(str(scanner_path))
except Exception as e:
    st.error(f"Failed to read scanner CSV: {e}\n\nTried: {scanner_path}")
    st.stop()

try:
    news_df = load_news(str(news_path))
except Exception as e:
    st.error(f"Failed to read news CSV: {e}\n\nTried: {news_path}")
    st.stop()

if "symbol" not in scanner_df.columns:
    st.error("Scanner CSV must have a 'symbol' column.")
    st.stop()

scanner_symbols = sorted(scanner_df["symbol"].dropna().unique().tolist())

# Filter news
news_recent = filter_news_last_days(news_df, days=days)
news_recent = news_recent[news_recent["symbol"].isin(scanner_symbols)]
if headline_search:
    news_recent = news_recent[news_recent["headline"].astype(str).str.contains(headline_search, case=False, na=False)]

summary = build_symbol_summary(scanner_df, news_recent)

# Minimal header line only
st.caption(
    f"{screener_label} • {len(scanner_symbols)} symbols • "
    f"{len(news_recent)} news rows (last {days}d) • "
    f"{int((summary['news_count'] > 0).sum())} symbols w/ news • "
    f"{int(news_recent['provider'].nunique()) if 'provider' in news_recent.columns else 0} providers"
)

# Build table
display = summary.copy()
display["Market Cap"] = display["market_cap"].apply(fmt_money) if "market_cap" in display.columns else "N/A"
display["Float"] = display["float_shares"].apply(fmt_num) if "float_shares" in display.columns else "N/A"
display["Shortable Shares"] = display["shortable_shares"].apply(fmt_num) if "shortable_shares" in display.columns else "N/A"
display["Trades/Min"] = display["trade_rate"].apply(fmt_num) if "trade_rate" in display.columns else "N/A"

if "effective_volume_per_min" in display.columns:
    display["Volume/Min"] = display["effective_volume_per_min"].apply(fmt_num)
elif "computed_volume_per_min" in display.columns:
    display["Volume/Min"] = display["computed_volume_per_min"].apply(fmt_num)
else:
    display["Volume/Min"] = "N/A"

display["Volume"] = display["volume"].apply(fmt_num) if "volume" in display.columns else "N/A"
display["Latest News (UTC)"] = pd.to_datetime(display.get("latest_news_time_utc", pd.NaT), utc=True, errors="coerce")
display["Latest News (UTC)"] = display["Latest News (UTC)"].dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")
display["Latest Headline"] = display.get("latest_headline", "").fillna("")

cols: List[str] = []
for c in ["symbol", "description", "last", "pct_change"]:
    if c in display.columns:
        cols.append(c)

cols += [
    "Shortable Shares", "Market Cap", "Float", "Trades/Min", "Volume/Min", "Volume",
    "Latest News (UTC)", "Latest Headline", "news_count"
]

final = display[cols].copy().rename(columns={
    "symbol": "Symbol",
    "description": "Description",
    "last": "Last",
    "pct_change": "% Change",
    "news_count": "News Count",
})

# Download
st.download_button(
    "Download CSV",
    data=final.to_csv(index=False).encode("utf-8"),
    file_name=f"{screener_slug}_scanner_latest_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
    mime="text/csv",
)

# No height => browser scroll only
st.dataframe(
    final,
    use_container_width=True,
    column_config={
        "Symbol": st.column_config.TextColumn("Symbol", width="small"),
        "Description": st.column_config.TextColumn("Description", width="medium"),
        "Latest Headline": st.column_config.TextColumn("Latest Headline", width="large"),
        "Latest News (UTC)": st.column_config.TextColumn("Latest News (UTC)", width="small"),
        "Market Cap": st.column_config.TextColumn("Market Cap", width="small"),
        "Float": st.column_config.TextColumn("Float", width="small"),
        "Shortable Shares": st.column_config.TextColumn("Shortable Shares", width="small"),
        "Trades/Min": st.column_config.TextColumn("Trades/Min", width="small"),
        "Volume/Min": st.column_config.TextColumn("Volume/Min", width="small"),
        "Volume": st.column_config.TextColumn("Volume", width="small"),
        "% Change": st.column_config.TextColumn("% Change", width="small"),
        "Last": st.column_config.TextColumn("Last", width="small"),
        "News Count": st.column_config.NumberColumn("News Count", width="small"),
    },
    hide_index=True,
)

# Headlines panel
st.markdown("---")
selected_symbol = st.selectbox("Headlines for", options=scanner_symbols, index=0, key="headline_symbol")

sym_news = news_recent[news_recent["symbol"] == selected_symbol].copy().sort_values("published_at_utc", ascending=False)
if sym_news.empty:
    st.caption("No headlines for this symbol in the selected window.")
else:
    sym_show = sym_news[["published_at_utc", "provider", "provider_name", "headline", "articleId"]].copy()
    sym_show["published_at_utc"] = sym_show["published_at_utc"].dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    sym_show = sym_show.rename(columns={
        "published_at_utc": "Published (UTC)",
        "provider": "Provider",
        "provider_name": "Provider Name",
        "headline": "Headline",
        "articleId": "Article ID",
    })

    st.dataframe(
        sym_show,
        use_container_width=True,
        column_config={
            "Headline": st.column_config.TextColumn("Headline", width="large"),
            "Provider Name": st.column_config.TextColumn("Provider Name", width="medium"),
            "Provider": st.column_config.TextColumn("Provider", width="small"),
            "Published (UTC)": st.column_config.TextColumn("Published (UTC)", width="small"),
        },
        hide_index=True,
    )
