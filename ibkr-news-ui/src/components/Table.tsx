// src/components/Table.tsx
import React, { useMemo, useState } from "react";
import type { ScreenerRow } from "../types";

type AnyRow = ScreenerRow & Record<string, any>;

function getFirst(row: AnyRow, keys: string[]) {
  for (const k of keys) {
    const v = row?.[k];
    if (v !== null && v !== undefined && v !== "") return v;
  }
  return "";
}

function toNum(v: any): number {
  const n = typeof v === "number" ? v : v == null || v === "" ? NaN : Number(v);
  return Number.isFinite(n) ? n : NaN;
}

function fmt(v: any, digits?: number) {
  if (v === null || v === undefined || v === "") return "";
  if (typeof v === "number") {
    if (Number.isFinite(v) && typeof digits === "number") return v.toFixed(digits);
    return String(v);
  }
  const n = toNum(v);
  if (Number.isFinite(n)) {
    if (typeof digits === "number") return n.toFixed(digits);
    return String(n);
  }
  return String(v);
}

type SortDir = "asc" | "desc";
type SortState = { key: string; dir: SortDir } | null;

function valForSort(v: unknown): string | number {
  const n = toNum(v as any);
  if (Number.isFinite(n)) return n;
  if (v == null) return "";
  return String(v).toLowerCase();
}

export function Table(props: { rows?: ScreenerRow[] | null; onRowClick: (row: ScreenerRow) => void }) {
  const rawRows = (props.rows ?? []) as AnyRow[];

  const [showAdvanced, setShowAdvanced] = useState(true);
  const [sort, setSort] = useState<SortState>({ key: "pct", dir: "desc" });

  const cols = useMemo(() => {
    const base = [
      { key: "symbol", label: "Symbol", w: 110, sortable: true },
      { key: "last", label: "Last", w: 90, sortable: true },
      { key: "pct", label: "%Chg", w: 90, sortable: true },

      // RelVol immediately after %Chg
      { key: "relvol", label: "RelVol", w: 105, sortable: true },

      // volumes (✅ add 1m)
      { key: "vol1", label: "Vol(1m)", w: 110, sortable: true },
      { key: "vol3", label: "Vol(3m)", w: 110, sortable: true },
      { key: "vol5", label: "Vol(5m)", w: 110, sortable: true },
      { key: "vol10", label: "Vol(10m)", w: 120, sortable: true },
      { key: "vol15", label: "Vol(15m)", w: 120, sortable: true },

      // trades (✅ add 1m)
      { key: "tr1", label: "Trades(1m)", w: 120, sortable: true },
      { key: "tr5", label: "Trades(5m)", w: 120, sortable: true },
      { key: "tr10", label: "Trades(10m)", w: 120, sortable: true },
      { key: "tr15", label: "Trades(15m)", w: 120, sortable: true },

      { key: "shortable", label: "Shortable", w: 120, sortable: true },

      // indicators (before news)
      { key: "rsi14", label: "RSI(14)", w: 95, sortable: true },
      { key: "macd", label: "MACD", w: 110, sortable: true },
      { key: "macdSig", label: "MACD Sig", w: 110, sortable: true },
      { key: "macdHist", label: "MACD Hist", w: 115, sortable: true },
    ];

    const adv = [
      { key: "vwap5d", label: "VWAP5 Dist", w: 115, sortable: true },
      { key: "vwap30d", label: "VWAP30 Dist", w: 125, sortable: true },
      { key: "vwap30", label: "VWAP(30m)", w: 120, sortable: true },
      { key: "accel", label: "Accel", w: 90, sortable: true },
      { key: "breakout", label: "Breakout", w: 110, sortable: true },
    ];

    const newsTail = [
      { key: "news", label: "News", w: 70, sortable: true },
      { key: "headline", label: "Latest Headline", w: 520, sortable: true },
    ];

    if (!showAdvanced) return [...base, ...newsTail];
    return [...base, ...adv, ...newsTail];
  }, [showAdvanced]);

  function extractForKey(r: AnyRow, key: string) {
    switch (key) {
      case "symbol":
        return getFirst(r, ["symbol", "ticker"]);
      case "last":
        return getFirst(r, ["last", "last_close", "lastPrice"]);
      case "pct":
        return getFirst(r, ["pctChange", "pct_change"]);

      case "relvol":
        return getFirst(r, ["relvol", "relVol", "relative_volume"]);

      case "rsi14":
        return getFirst(r, ["rsi14", "rsi"]);
      case "macd":
        return getFirst(r, ["macd"]);
      case "macdSig":
        return getFirst(r, ["macd_signal", "macdSignal"]);
      case "macdHist":
        return getFirst(r, ["macd_hist", "macdHist"]);

      // ✅ Vol(1m)
      case "vol1":
        return getFirst(r, ["vol_1m", "vol1m", "Vol(1m)"]);

      case "vol3":
        return getFirst(r, ["vol_3m", "vol3m", "Vol(3m)"]);
      case "vol5":
        return getFirst(r, ["vol_5m", "vol5m", "Vol(5m)"]);
      case "vol10":
        return getFirst(r, ["vol_10m", "vol10m", "Vol(10m)"]);

      // ✅ Vol(15m): use real if present; fallback to old estimate
      case "vol15": {
        const real = getFirst(r, ["vol_15m", "vol15m", "Vol(15m)"]);
        if (real !== "" && real !== null && real !== undefined) return real;
        const v10 = toNum(getFirst(r, ["vol_10m", "vol10m", "Vol(10m)"]));
        return Number.isFinite(v10) ? v10 * 1.5 : "";
      }

      // ✅ Trades(1m)
      case "tr1":
        return getFirst(r, ["trades_1m", "trades1m", "Trades(1m)"]);

      case "tr5":
        return getFirst(r, ["trades5m", "trades_5m", "Trades(5m)"]);
      case "tr10":
        return getFirst(r, ["trades10m", "trades_10m", "Trades(10m)"]);

      // ✅ Trades(15m): use real if present; fallback to old estimate
      case "tr15": {
        const real = getFirst(r, ["trades15m", "trades_15m", "Trades(15m)"]);
        if (real !== "" && real !== null && real !== undefined) return real;
        const t10 = toNum(getFirst(r, ["trades10m", "trades_10m", "Trades(10m)"]));
        return Number.isFinite(t10) ? (t10 / 10) * 15 : "";
      }

      case "shortable":
        return getFirst(r, ["shortableShares", "shortable_shares"]);

      case "vwap30":
        return getFirst(r, ["vwap_30m", "vwap30m", "VWAP(30m)"]);
      case "vwap5d":
        return getFirst(r, ["vwap5_dist", "vwap5Dist", "VWAP5 Dist"]);
      case "vwap30d":
        return getFirst(r, ["vwap30_dist", "vwap30Dist", "VWAP30 Dist"]);

      case "accel":
        return getFirst(r, ["accel"]);
      case "breakout":
        return getFirst(r, ["breakoutScore"]);

      case "news":
        return getFirst(r, ["newsCount"]);
      case "headline":
        return getFirst(r, ["latestHeadline", "latest_headline"]);

      default:
        return r?.[key];
    }
  }

  function toggleSort(key: string) {
    setSort((p) => (!p || p.key !== key ? { key, dir: "desc" } : { key, dir: p.dir === "desc" ? "asc" : "desc" }));
  }

  function sortIcon(key: string) {
    if (!sort || sort.key !== key) return "↕";
    return sort.dir === "asc" ? "↑" : "↓";
  }

  const rows = useMemo(() => {
    if (!sort) return rawRows;
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...rawRows].sort((a, b) => {
      const av = valForSort(extractForKey(a, sort.key));
      const bv = valForSort(extractForKey(b, sort.key));
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return 0;
    });
  }, [rawRows, sort]);

  return (
    <div style={styles.wrap}>
      <div style={styles.tableTop}>
        <div style={{ fontWeight: 900 }}>Results</div>
        <button onClick={() => setShowAdvanced((v) => !v)} style={styles.toggleBtn}>
          {showAdvanced ? "Hide New Fields" : "Show New Fields"}
        </button>
      </div>

      <table style={styles.table}>
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c.key} style={{ ...styles.th, minWidth: c.w }} onClick={() => toggleSort(c.key)}>
                {c.label} <span style={{ color: "#94a3b8" }}>{sortIcon(c.key)}</span>
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {rows.map((r, i) => (
            <tr key={i} style={styles.tr} onClick={() => props.onRowClick(r)}>
              {cols.map((c) => (
                <td key={c.key} style={styles.td}>
                  {fmt(
                    extractForKey(r, c.key),
                    c.key === "rsi14"
                      ? 1
                      : c.key.startsWith("macd")
                      ? 4
                      : c.key === "relvol"
                      ? 2
                      : c.key === "pct"
                      ? 2
                      : c.key === "last"
                      ? 2
                      : 0
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  wrap: { overflow: "auto", border: "1px solid #e5e7eb", borderRadius: 14, background: "white", height: "100%" },
  tableTop: { position: "sticky", top: 0, background: "white", padding: 10, display: "flex", justifyContent: "space-between" },
  toggleBtn: { padding: "8px 10px", borderRadius: 10, border: "1px solid #e5e7eb", background: "white", fontWeight: 800 },
  table: { width: "100%", borderCollapse: "separate", borderSpacing: 0 },
  th: { padding: 12, fontSize: 12, borderBottom: "1px solid #e5e7eb", whiteSpace: "nowrap", cursor: "pointer" },
  tr: { cursor: "pointer" },
  td: { padding: 12, borderBottom: "1px solid #f1f5f9", whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" },
};
