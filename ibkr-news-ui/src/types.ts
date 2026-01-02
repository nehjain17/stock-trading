export type Screener = "most_active" | "top_gainers" | "top_losers";

export interface ScreenerRow {
  symbol: string;
  description: string;
  last: string | number | null;
  pctChange: string | number | null;
  shortableShares: string | number | null;
  marketCap: string | number | null;
  floatShares: string | number | null;
  tradesPerMin: string | number | null;
  volumePerMin: string | number | null;
  volume: string | number | null;
  latestNewsUtc: string | null;       // "2025-12-31 22:24:16"
  latestHeadline: string | null;
  newsCount: number;
}

export interface ScreenerResponse {
  screener: Screener;
  screenerLabel: string;
  days: number;
  symbols: number;
  newsRows: number;
  symbolsWithNews: number;
  providers: number;
  rows: ScreenerRow[];
}

export interface HeadlineItem {
  symbol: string;
  publishedUtc: string;   // "2025-12-31 22:24:16"
  provider: string;
  providerName: string;
  headline: string;
  articleId?: string | null;
}

export interface HeadlinesResponse {
  symbol: string;
  days: number;
  items: HeadlineItem[];
}
