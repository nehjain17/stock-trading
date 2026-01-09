// src/components/Sidebar.tsx
import React from "react";
import type { Screener } from "../types";

const SCREENERS: { label: string; value: Screener }[] = [
  { label: "All (Merged)", value: "all" },
  { label: "Most Active", value: "most_active" },
  { label: "Top % Gainers", value: "top_gainers" },
  { label: "Top % Losers", value: "top_losers" },
  { label: "Top Volume", value: "top_volume" },
  { label: "Top Trade Rate", value: "top_trade_rate" },
];

export function Sidebar(props: {
  screener: Screener;
  setScreener: (v: Screener) => void;

  days: number;
  setDays: (n: number) => void;

  search: string;
  setSearch: (s: string) => void;

  // fast reload (reads existing CSVs)
  onRefreshTable: () => void;
  loading?: boolean;

  // slow refresh (runs scripts)
  onRefreshData: () => void;
  refreshingData?: boolean;

  refreshScanner: boolean;
  setRefreshScanner: (v: boolean) => void;

  providers: Record<string, boolean>;
  setProvider: (key: string, v: boolean) => void;

  limit: number;
  setLimit: (n: number) => void;

  dedupeAllBySymbol: boolean;
  setDedupeAllBySymbol: (v: boolean) => void;
}) {
  const {
    screener,
    setScreener,
    days,
    setDays,
    search,
    setSearch,
    onRefreshTable,
    loading,
    onRefreshData,
    refreshingData,
    refreshScanner,
    setRefreshScanner,
    providers,
    setProvider,
    limit,
    setLimit,
    dedupeAllBySymbol,
    setDedupeAllBySymbol,
  } = props;

  const disabled = !!loading || !!refreshingData;

  return (
    <aside style={styles.sidebar}>
      <div style={styles.title}>Stock Scanner</div>

      <div style={styles.section}>
        <div style={styles.sectionTitle}>Screeners</div>

        <label style={styles.label}>Screener</label>
        <select
          value={screener}
          onChange={(e) => setScreener(e.target.value as Screener)}
          style={styles.select}
          disabled={disabled}
        >
          {SCREENERS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>

        <label style={styles.label}>Days</label>
        <input
          type="number"
          min={1}
          max={30}
          value={days}
          onChange={(e) => setDays(Math.max(1, Math.min(30, Number(e.target.value || 1))))}
          style={styles.input}
          disabled={disabled}
        />

        <label style={styles.label}>Search (headline contains)</label>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="earnings, FDA, merger…"
          style={styles.input}
          disabled={disabled}
        />

        <button onClick={onRefreshTable} style={styles.button} disabled={disabled}>
          {loading ? "Loading…" : "Refresh Table"}
        </button>
      </div>

      <div style={styles.section}>
        <div style={styles.sectionTitle}>Refresh Data (run scripts)</div>

        <label style={styles.checkRow}>
          <input
            type="checkbox"
            checked={refreshScanner}
            onChange={(e) => setRefreshScanner(e.target.checked)}
            disabled={disabled}
          />
          <span>Refresh scanner CSV</span>
        </label>

        <div style={{ marginTop: 8, fontWeight: 700, fontSize: 12, opacity: 0.75 }}>
          Providers
        </div>

        {Object.keys(providers).map((k) => (
          <label key={k} style={styles.checkRow}>
            <input
              type="checkbox"
              checked={!!providers[k]}
              onChange={(e) => setProvider(k, e.target.checked)}
              disabled={disabled}
            />
            <span>{k}</span>
          </label>
        ))}

        <label style={styles.label}>Limit</label>
        <input
          type="number"
          min={1}
          max={500}
          value={limit}
          onChange={(e) => setLimit(Math.max(1, Math.min(500, Number(e.target.value || 50))))}
          style={styles.input}
          disabled={disabled}
        />

        {screener === "all" && (
          <label style={styles.checkRow}>
            <input
              type="checkbox"
              checked={dedupeAllBySymbol}
              onChange={(e) => setDedupeAllBySymbol(e.target.checked)}
              disabled={disabled}
            />
            <span>Dedupe “All” by symbol</span>
          </label>
        )}

        <button onClick={onRefreshData} style={styles.primaryButton} disabled={disabled}>
          {refreshingData ? "Refreshing…" : "Refresh Data"}
        </button>

        <div style={styles.note}>
          Refresh Table = just reads current CSVs. Refresh Data = runs IBKR/news scripts and updates CSVs.
        </div>
      </div>
    </aside>
  );
}

const styles: Record<string, React.CSSProperties> = {
  sidebar: {
    width: 320,
    minWidth: 320,
    maxWidth: 360,
    height: "100vh",
    overflow: "auto",
    borderRight: "1px solid #e5e7eb",
    padding: 14,
    background: "#f8fafc",
  },
  title: {
    fontWeight: 900,
    fontSize: 16,
    marginBottom: 10,
  },
  section: {
    background: "white",
    border: "1px solid #e5e7eb",
    borderRadius: 14,
    padding: 12,
    marginBottom: 12,
  },
  sectionTitle: { fontWeight: 800, marginBottom: 8 },
  label: { display: "block", fontSize: 12, opacity: 0.8, marginTop: 10, marginBottom: 6 },
  input: {
    width: "100%",
    padding: "10px 10px",
    borderRadius: 10,
    border: "1px solid #d1d5db",
    outline: "none",
    background: "white",
  },
  select: {
    width: "100%",
    padding: "10px 10px",
    borderRadius: 10,
    border: "1px solid #d1d5db",
    background: "white",
  },
  button: {
    width: "100%",
    marginTop: 12,
    padding: "10px 12px",
    borderRadius: 10,
    border: "1px solid #d1d5db",
    background: "white",
    cursor: "pointer",
    fontWeight: 700,
  },
  primaryButton: {
    width: "100%",
    marginTop: 12,
    padding: "10px 12px",
    borderRadius: 10,
    border: "1px solid #111827",
    background: "#111827",
    color: "white",
    cursor: "pointer",
    fontWeight: 800,
  },
  checkRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    fontSize: 13,
    marginTop: 8,
  },
  note: {
    marginTop: 10,
    fontSize: 12,
    opacity: 0.75,
    lineHeight: 1.35,
  },
};
