// src/App.tsx
import React, { useEffect, useMemo, useRef, useState } from "react";
import type { ScreenerResponse, ScreenerRow } from "./types";
import { Table } from "./components/Table";

/** ✅ YOUR screener IDs */
const DEFAULT_SCREENERS: Array<{ id: string; label: string }> = [
  { id: "most_active", label: "Most Active" },
  { id: "top_gainers", label: "Top % Gainers" },
  { id: "top_losers", label: "Top % Losers" },
  { id: "top_trade_rate", label: "Top Trade Rate" },
];

const PROVIDERS: Array<{ id: string; label: string }> = [
  { id: "all", label: "All" },
  { id: "ibkr", label: "ibkr" },
  { id: "benzinga", label: "benzinga" },
  { id: "finnhub", label: "finnhub" },
  { id: "polygon", label: "polygon" },
];

/**
 * If FastAPI is on :8000 and Vite is :5173:
 *   export VITE_API_BASE="http://localhost:8000"
 */
const API_BASE: string = (import.meta as any)?.env?.VITE_API_BASE ?? "";

function safeArr<T>(v: any): T[] {
  return Array.isArray(v) ? v : [];
}

function normalizeResponse(raw: any, fallback: { screener: string; days: number }): ScreenerResponse {
  const r: ScreenerResponse = raw ?? ({} as any);
  const rows: ScreenerRow[] = Array.isArray(r?.rows) ? r.rows : Array.isArray(raw) ? raw : [];

  const screener = r?.screener ?? fallback.screener;
  const screenerLabel =
    r?.screenerLabel ?? DEFAULT_SCREENERS.find((s) => s.id === screener)?.label ?? screener;

  return {
    screener,
    screenerLabel,
    days: r?.days ?? fallback.days,

    symbols: Number.isFinite(r?.symbols as any) ? (r.symbols as number) : rows.length,
    newsRows: Number.isFinite(r?.newsRows as any) ? (r.newsRows as number) : 0,
    symbolsWithNews: Number.isFinite(r?.symbolsWithNews as any) ? (r.symbolsWithNews as number) : 0,
    providers: Number.isFinite(r?.providers as any) ? (r.providers as number) : 0,

    rows,

    scannerFiles: safeArr<string>(r?.scannerFiles),
    newsFiles: safeArr<string>(r?.newsFiles),
    warnings: safeArr<string>(r?.warnings),
  };
}

export default function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const [screener, setScreener] = useState(DEFAULT_SCREENERS[1].id); // top_gainers
  const [days, setDays] = useState<number>(3);
  const [limit, setLimit] = useState<number>(50);
  const [query, setQuery] = useState<string>("");

  const [providerChoice, setProviderChoice] = useState<string>("all");
  const [refreshScannerCsv, setRefreshScannerCsv] = useState<boolean>(true);

  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>("");

  const [data, setData] = useState<ScreenerResponse | null>(null);

  const [jobRunning, setJobRunning] = useState<boolean>(false);
  const [showLogs, setShowLogs] = useState<boolean>(false);
  const [hasRunRefresh, setHasRunRefresh] = useState<boolean>(false);
  const [logs, setLogs] = useState<string>('Tip: Click "Refresh Data". Log output will appear here.\n');
  const logsRef = useRef<HTMLDivElement | null>(null);

  function appendLog(line: string) {
    setLogs((prev) => prev + line.replace(/\n?$/, "\n"));
  }

  useEffect(() => {
    if (!showLogs) return;
    const el = logsRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logs, showLogs]);

  function buildProvidersParam(): string | null {
    if (providerChoice === "all") return null; // omit = all
    return providerChoice;
  }

  async function fetchScreener() {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("screener", screener);
      params.set("days", String(days));
      params.set("limit", String(limit));
      if (query.trim()) params.set("q", query.trim());

      const p = buildProvidersParam();
      if (p) params.set("providers", p);

      // read CSVs only; do not rerun scripts here
      params.set("refresh_scanner_csv", "0");

      const url = `${API_BASE}/api/screener?${params.toString()}`;
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`API error: ${resp.status} ${resp.statusText}`);

      const json = await resp.json();
      setData(normalizeResponse(json, { screener, days }));
    } catch (e: any) {
      setError(e?.message ?? String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  async function runRefreshJob() {
    setJobRunning(true);
    setHasRunRefresh(true);
    setShowLogs(true);
    appendLog(`\n=== Refresh started (${new Date().toLocaleTimeString()}) ===`);

    try {
      const params = new URLSearchParams();
      params.set("screener", screener);
      params.set("days", String(days));
      params.set("limit", String(limit));

      const p = buildProvidersParam();
      if (p) params.set("providers", p);

      params.set("refresh_scanner_csv", refreshScannerCsv ? "1" : "0");

      const url = `${API_BASE}/api/refresh?${params.toString()}`;
      const resp = await fetch(url);

      if (!resp.ok) throw new Error(`Refresh API error: ${resp.status} ${resp.statusText}`);

      const text = await resp.text();
      appendLog(text || "(refresh ok)");
    } catch (e: any) {
      appendLog(`ERROR: ${e?.message ?? String(e)}`);
    } finally {
      appendLog(`=== Refresh finished (${new Date().toLocaleTimeString()}) ===\n`);
      setJobRunning(false);
      await fetchScreener();
    }
  }

  // auto-load once
  useEffect(() => {
    fetchScreener();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const headerMeta = useMemo(() => {
    const label =
      data?.screenerLabel ?? DEFAULT_SCREENERS.find((s) => s.id === screener)?.label ?? screener;
    return {
      screenerLabel: label,
      symbols: data?.symbols ?? 0,
      newsRows: data?.newsRows ?? 0,
      symbolsWithNews: data?.symbolsWithNews ?? 0,
      providers: data?.providers ?? 0,
      scannerFiles: data?.scannerFiles ?? [],
      newsFiles: data?.newsFiles ?? [],
      warnings: data?.warnings ?? [],
    };
  }, [data, screener]);

  const filteredRows = useMemo(() => {
    const rows = data?.rows ?? [];
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => {
      const sym = String(r.symbol ?? (r as any).ticker ?? "").toLowerCase();
      const head = String((r as any).latestHeadline ?? "").toLowerCase();
      return sym.includes(q) || head.includes(q);
    });
  }, [data, query]);

  const sidebarStyle: React.CSSProperties = sidebarCollapsed ? { width: 58 } : { width: 360 };

  return (
    <div
      style={{
        fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif",
        background: "#f8fafc",
        minHeight: "100vh",
      }}
    >
      <style>{`
        .wrap { display:flex; align-items: flex-start; }
        .side { background:#fff; border-right:1px solid #e5e7eb; min-height:100vh; padding:12px; box-sizing:border-box; transition: width .15s ease; }
        .main { flex:1; padding:24px; }
        .card { background:#fff; border:1px solid #e5e7eb; border-radius:12px; padding:16px; margin-bottom:16px; }
        .btn { border:1px solid #e5e7eb; background:#fff; padding:8px 12px; border-radius:10px; font-weight:700; cursor:pointer; }
        .btn:disabled { background:#f1f5f9; color:#94a3b8; cursor:not-allowed; }
        .btnPrimary { background:#0f172a; color:#fff; border:0; }
        .btnPrimary:disabled { background:#94a3b8; }
        .label { font-size:12px; color:#475569; margin-top:10px; }
        .inp, .sel { width:100%; box-sizing:border-box; padding:8px 10px; border:1px solid #e5e7eb; border-radius:10px; margin-top:6px; }
        .hrow { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:10px; }
        .title { font-size:20px; font-weight:900; }
        .sub { font-size:13px; color:#64748b; margin-top:2px; }
        .logs { height:240px; overflow:auto; border-radius:12px; background:#0b1220; color:#e2e8f0; padding:12px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size:12px; white-space:pre; }
        .warn { margin-top:10px; background:#fffbeb; border:1px solid #fde68a; color:#92400e; padding:10px; border-radius:10px; }
        .files { margin-top:10px; font-size:12px; color:#475569; }
        .badge { display:inline-block; padding:2px 8px; border-radius:999px; background:#f1f5f9; margin-right:6px; }
      `}</style>

      <div className="wrap">
        {/* sidebar */}
        <div className="side" style={sidebarStyle}>
          <div className="hrow">
            {!sidebarCollapsed && <div className="title">Stock Scanner</div>}
            <button
              className="btn"
              onClick={() => setSidebarCollapsed((v) => !v)}
              title={sidebarCollapsed ? "Expand" : "Collapse"}
            >
              {sidebarCollapsed ? "»" : "«"}
            </button>
          </div>

          {sidebarCollapsed ? null : (
            <>
              <div className="card">
                <div style={{ fontWeight: 800, marginBottom: 10 }}>Screeners</div>

                <div className="label">Screener</div>
                <select className="sel" value={screener} onChange={(e) => setScreener(e.target.value)}>
                  {DEFAULT_SCREENERS.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label}
                    </option>
                  ))}
                </select>

                <div className="label">Days</div>
                <input
                  className="inp"
                  type="number"
                  min={1}
                  max={30}
                  value={days}
                  onChange={(e) => setDays(Number(e.target.value || 1))}
                />

                <div className="label">Limit</div>
                <input
                  className="inp"
                  type="number"
                  min={1}
                  max={200}
                  value={limit}
                  onChange={(e) => setLimit(Number(e.target.value || 50))}
                />

                <div className="label">Search (symbol/headline)</div>
                <input
                  className="inp"
                  placeholder="WDC, FDA, merger..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />

                <div style={{ marginTop: 10, display: "flex", gap: 10 }}>
                  <button className="btn" onClick={fetchScreener} disabled={loading}>
                    {loading ? "Loading..." : "Refresh Table"}
                  </button>
                </div>

                <div className="sub" style={{ marginTop: 10 }}>
                  Table refresh reads current CSVs (no scripts).
                </div>
              </div>

              <div className="card">
                <div style={{ fontWeight: 800, marginBottom: 10 }}>Refresh Data (run scripts)</div>

                <div className="label">Providers</div>
                <select className="sel" value={providerChoice} onChange={(e) => setProviderChoice(e.target.value)}>
                  {PROVIDERS.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>

                <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 10, fontSize: 13 }}>
                  <input
                    type="checkbox"
                    checked={refreshScannerCsv}
                    onChange={(e) => setRefreshScannerCsv(e.target.checked)}
                  />
                  Refresh scanner CSV
                </label>

                <button
                  className="btn btnPrimary"
                  onClick={runRefreshJob}
                  disabled={jobRunning}
                  style={{ marginTop: 10 }}
                >
                  {jobRunning ? "Refreshing..." : "Refresh Data"}
                </button>

                <div className="sub" style={{ marginTop: 10, lineHeight: 1.4 }}>
                  Refresh Data runs scripts and updates CSVs.
                </div>
              </div>
            </>
          )}
        </div>

        {/* main */}
        <div className="main">
          <div className="card">
            <div className="hrow">
              <div>
                <div style={{ fontSize: 18, fontWeight: 900 }}>{headerMeta.screenerLabel}</div>
                <div className="sub">
                  Symbols: {headerMeta.symbols} · News rows: {headerMeta.newsRows} · With news:{" "}
                  {headerMeta.symbolsWithNews} · Providers: {headerMeta.providers}
                  {API_BASE ? ` · API: ${API_BASE}` : ""}
                </div>

                {headerMeta.scannerFiles.length || headerMeta.newsFiles.length ? (
                  <div className="files">
                    {headerMeta.scannerFiles.length ? (
                      <div style={{ marginTop: 6 }}>
                        <span className="badge">scannerFiles</span> {headerMeta.scannerFiles.join(", ")}
                      </div>
                    ) : null}
                    {headerMeta.newsFiles.length ? (
                      <div style={{ marginTop: 6 }}>
                        <span className="badge">newsFiles</span> {headerMeta.newsFiles.join(", ")}
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {headerMeta.warnings.length ? (
                  <div className="warn">
                    <b>Warnings</b>
                    <div style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{headerMeta.warnings.join("\n")}</div>
                  </div>
                ) : null}
              </div>

              <button
                className="btn"
                onClick={() => hasRunRefresh && setShowLogs((v) => !v)}
                disabled={!hasRunRefresh}
                title={!hasRunRefresh ? "Run Refresh Data to enable logs" : ""}
              >
                {showLogs ? "Hide Logs" : "Show Logs"}
              </button>
            </div>
          </div>

          {error && (
            <div className="card" style={{ background: "#fef2f2", border: "1px solid #fecaca", color: "#b91c1c" }}>
              {error}
            </div>
          )}

          {showLogs && hasRunRefresh && (
            <div className="card">
              <div className="hrow">
                <div style={{ fontWeight: 900 }}>Refresh Logs</div>
                <div className="sub">{jobRunning ? "Job running" : "No job running"}</div>
              </div>
              <div ref={logsRef} className="logs">
                {logs}
              </div>
            </div>
          )}

          {/* ✅ IMPORTANT: remove fixed height frame; let browser scroll */}
          <div className="card">
            <Table
              rows={filteredRows}
              onRowClick={(row) => {
                console.log("row clicked", row);
              }}
            />
          </div>

          <div className="sub" style={{ marginTop: 10 }}>
            Tip: “Hide New Fields” toggles VWAP/HighPrev/VPMBase/Accel/Breakout/Shortable.
          </div>
        </div>
      </div>
    </div>
  );
}
