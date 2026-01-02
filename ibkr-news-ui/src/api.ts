import type { Screener, ScreenerResponse, HeadlinesResponse } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

function qs(params: Record<string, any>) {
  const u = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    u.set(k, String(v));
  });
  return u.toString();
}

export async function fetchScreener(params: {
  screener: Screener;
  days: number;
  search?: string;
}): Promise<ScreenerResponse> {
  const url = `${API_BASE}/api/screener?${qs(params)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load screener: ${res.status}`);
  return res.json();
}

export async function fetchHeadlines(params: {
  screener: Screener;
  days: number;
  symbol: string;
  search?: string;
}): Promise<HeadlinesResponse> {
  const url = `${API_BASE}/api/headlines?${qs(params)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load headlines: ${res.status}`);
  return res.json();
}
