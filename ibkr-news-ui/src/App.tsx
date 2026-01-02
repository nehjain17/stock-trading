import React, { useEffect, useState } from "react";
import type { HeadlineItem, Screener, ScreenerResponse, ScreenerRow } from "./types";
import { fetchHeadlines, fetchScreener } from "./api";
import { Sidebar } from "./components/Sidebar";
import { Table } from "./components/Table";
import { Drawer } from "./components/Drawer";

function screenerLabel(s: Screener) {
  if (s === "most_active") return "Most Active";
  if (s === "top_gainers") return "Top % Gainers";
  if (s === "top_losers") return "Top % Losers";
  return s;
}

export default function App() {
  const [screener, setScreener] = useState<Screener>("most_active");
  const [days, setDays] = useState<number>(3);
  const [search, setSearch] = useState<string>("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [data, setData] = useState<ScreenerResponse | null>(null);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [drawerError, setDrawerError] = useState<string | null>(null);
  const [drawerItems, setDrawerItems] = useState<HeadlineItem[]>([]);
  const [drawerTitle, setDrawerTitle] = useState<string>("");

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchScreener({ screener, days, search });

      // IMPORTANT: guard in case backend returns a different shape
      const safe: ScreenerResponse = {
        ...res,
        rows: Array.isArray((res as any)?.rows) ? (res as any).rows : [],
      };

      setData(safe);
    } catch (e: any) {
      setError(e?.message ?? "Failed to load");
      // keep old data; or setData(null) if you prefer:
      // setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screener, days]); // auto reload on screener/days change

  const onRefresh = () => load();

  const onRowClick = async (row: ScreenerRow) => {
    setDrawerOpen(true);
    setDrawerLoading(true);
    setDrawerError(null);
    setDrawerItems([]);
    setDrawerTitle(`${row.symbol} — Headlines (last ${days}d)`);
    try {
      const res = await fetchHeadlines({ screener, days, symbol: row.symbol, search });
      setDrawerItems(Array.isArray(res.items) ? res.items : []);
    } catch (e: any) {
      setDrawerError(e?.message ?? "Failed to load headlines");
    } finally {
      setDrawerLoading(false);
    }
  };

  // Always pass an array so Table never crashes
  const rows = data?.rows ?? [];

  return (
    <div style={styles.shell}>
      <Sidebar
        screener={screener}
        setScreener={setScreener}
        days={days}
        setDays={setDays}
        search={search}
        setSearch={setSearch}
        onRefresh={onRefresh}
        loading={loading}
      />

      <main style={styles.main}>
        <div style={styles.topLine}>
          <div style={styles.title}>IBKR Scanner + News</div>
          <div style={styles.subtitle}>
            {data
              ? `${screenerLabel(data.screener)} • ${data.symbols} symbols • ${data.newsRows} news rows (last ${data.days}d) • ${data.symbolsWithNews} symbols w/ news • ${data.providers} providers`
              : `${screenerLabel(screener)} • ${loading ? "loading…" : "—"}`}
          </div>
        </div>

        {error && <div style={styles.error}>{error}</div>}

        <div style={{ marginTop: 12 }}>
          <div style={styles.actions}>
            <button style={styles.btn} onClick={onRefresh} disabled={loading}>
              {loading ? "Loading…" : "Refresh"}
            </button>

            <button
              style={styles.btn}
              disabled={!rows.length}
              onClick={() => {
                const blob = new Blob([toCsv(rows)], { type: "text/csv;charset=utf-8" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = `${(data?.screener ?? screener)}_scanner_latest_news.csv`;
                a.click();
                URL.revokeObjectURL(url);
              }}
            >
              Download CSV
            </button>
          </div>

          <Table rows={rows} onRowClick={onRowClick} />
        </div>
      </main>

      <Drawer
        open={drawerOpen}
        title={drawerTitle}
        onClose={() => setDrawerOpen(false)}
        loading={drawerLoading}
        error={drawerError}
        items={drawerItems}
      />
    </div>
  );
}

function toCsv(rows: any[]) {
  if (!rows.length) return "";
  const headers = Object.keys(rows[0]);
  const esc = (v: any) => `"${String(v ?? "").replaceAll(`"`, `""`)}"`;
  const lines = [headers.join(","), ...rows.map((r) => headers.map((h) => esc(r[h])).join(","))];
  return lines.join("\n");
}

const styles: Record<string, React.CSSProperties> = {
  shell: { display: "flex", minHeight: "100vh", background: "#f8fafc" },
  main: { flex: 1, padding: 16, maxWidth: "100%" },
  topLine: { marginBottom: 6 },
  title: { fontWeight: 900, fontSize: 18 },
  subtitle: { fontSize: 12, opacity: 0.7, marginTop: 2 },
  actions: { display: "flex", gap: 10, alignItems: "center", marginBottom: 10 },
  btn: {
    padding: "8px 12px",
    borderRadius: 10,
    border: "1px solid #d1d5db",
    background: "white",
    cursor: "pointer",
    fontWeight: 700,
  },
  error: { color: "#b91c1c", fontWeight: 800, marginTop: 8 },
};
