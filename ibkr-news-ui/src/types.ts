// src/types.ts
export type ScreenerRow = {
  screener?: string | null;
  screenerLabel?: string | null;

  symbol?: string;
  ticker?: string;

  last?: number | null;
  prevClose?: number | null;
  pctChange?: number | null;

  // snake_case (if backend ever returns)
  vol_10m?: number | null;
  vpm_10m?: number | null;
  trades_10m?: number | null;

  vwap_30m?: number | null;
  high_prev_30m?: number | null;
  vpm_base?: number | null;
  accel?: number | null;
  breakout_score?: number | null;

  // camelCase (your backend currently returns these too)
  vol10m?: number | null;
  vpm10m?: number | null;
  trades10m?: number | null;

  vwap30m?: number | null;
  highPrev30m?: number | null;
  vpmBase?: number | null;
  breakoutScore?: number | null;

  // news
  newsCount?: number | null;
  latestNewsUtc?: string | null;
  latestHeadline?: string | null;

  // optional
  shortable_shares?: number | null;
  shortableShares?: number | null;

  // allow extra fields
  [k: string]: any;
};

export type ScreenerResponse = {
  screener: string;
  screenerLabel?: string;
  days: number;

  symbols?: number;
  newsRows?: number;
  symbolsWithNews?: number;
  providers?: number;

  rows: ScreenerRow[];

  scannerFiles?: string[];
  newsFiles?: string[];
  warnings?: string[];
};
