// src/api.ts
import type {
  HeadlinesResponse,
  RefreshRequest,
  RefreshStartResponse,
  RefreshStatusResponse,
  ScreenerResponse,
  Screener,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!res.ok) {
    const msg =
      (data && typeof data === "object" && (data.detail || data.error)) ||
      `HTTP ${res.status} ${res.statusText}`;
    throw new Error(msg);
  }

  return data as T;
}

export async function fetchScreener(params: {
  screener: Screener;
  days: number;
  search: string;
  dedupeAllBySymbol?: boolean;
}): Promise<ScreenerResponse> {
  const q = new URLSearchParams();
  q.set("screener", params.screener);
  q.set("days", String(params.days));
  if (params.search) q.set("search", params.search);
  if (params.screener === "all") {
    q.set("dedupe_all_by_symbol", String(params.dedupeAllBySymbol ?? true));
  }

  const res = await http<ScreenerResponse>(`/api/screener?${q.toString()}`);

  // backend may return {error: "..."}
  if ((res as any)?.error) throw new Error((res as any).error);

  return res;
}

export async function fetchHeadlines(params: {
  screener: Screener;
  days: number;
  symbol: string;
  search: string;
}): Promise<HeadlinesResponse> {
  const q = new URLSearchParams();
  q.set("screener", params.screener);
  q.set("days", String(params.days));
  q.set("symbol", params.symbol);
  if (params.search) q.set("search", params.search);

  const res = await http<HeadlinesResponse>(`/api/headlines?${q.toString()}`);
  if ((res as any)?.error) throw new Error((res as any).error);
  return res;
}

export async function startRefresh(body: RefreshRequest): Promise<RefreshStartResponse> {
  return http<RefreshStartResponse>(`/api/refresh`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getRefreshStatus(jobId: string): Promise<RefreshStatusResponse> {
  return http<RefreshStatusResponse>(`/api/refresh/${encodeURIComponent(jobId)}`);
}

export async function cancelRefresh(jobId: string): Promise<{ jobId: string; status: string }> {
  return http<{ jobId: string; status: string }>(
    `/api/refresh/${encodeURIComponent(jobId)}/cancel`,
    { method: "POST" }
  );
}
