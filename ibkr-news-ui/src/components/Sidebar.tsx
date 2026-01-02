import React from "react";
import type { Screener } from "../types";

const SCREENERS: { label: string; value: Screener }[] = [
  { label: "Most Active", value: "most_active" },
  { label: "Top % Gainers", value: "top_gainers" },
  { label: "Top % Losers", value: "top_losers" },
];

export function Sidebar(props: {
  screener: Screener;
  setScreener: (v: Screener) => void;
  days: number;
  setDays: (n: number) => void;
  search: string;
  setSearch: (s: string) => void;
  onRefresh: () => void;
  loading?: boolean;
}) {
  const { screener, setScreener, days, setDays, search, setSearch, onRefresh, loading } = props;

  return (
    <aside style={styles.sidebar}>
      <div style={styles.sectionTitle}>Screeners</div>

      <label style={styles.label}>Screener</label>
      <select
        value={screener}
        onChange={(e) => setScreener(e.target.value as Screener)}
        style={styles.select}
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
      />

      <label style={styles.label}>Search</label>
      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="headline contains…"
        style={styles.input}
      />

      <button onClick={onRefresh} style={styles.button} disabled={loading}>
        {loading ? "Loading…" : "Refresh"}
      </button>
    </aside>
  );
}

const styles: Record<string, React.CSSProperties> = {
  sidebar: {
    width: 220,
    minWidth: 220,
    padding: 16,
    borderRight: "1px solid #e5e7eb",
    position: "sticky",
    top: 0,
    height: "100vh",
    background: "#f8fafc",
  },
  sectionTitle: { fontWeight: 700, marginBottom: 12 },
  label: { display: "block", fontSize: 12, opacity: 0.8, marginTop: 12, marginBottom: 6 },
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
    marginTop: 14,
    padding: "10px 12px",
    borderRadius: 10,
    border: "1px solid #d1d5db",
    background: "white",
    cursor: "pointer",
    fontWeight: 600,
  },
};
