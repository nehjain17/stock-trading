import React from "react";
import type { ScreenerRow } from "../types";

function cell(v: any) {
  if (v === null || v === undefined || v === "") return "—";
  return String(v);
}

// Safety net: strip IBKR headline metadata like "{A:...}* "
const HEAD_PREFIX_RE = /^\s*\{A:[^}]*\}\s*\*?\s*/;
function cleanHeadline(v: any) {
  const s = cell(v);
  if (s === "—") return s;
  let out = s;
  // Sometimes the prefix can appear more than once; strip a few times
  for (let i = 0; i < 3; i++) {
    const next = out.replace(HEAD_PREFIX_RE, "").trim();
    if (next === out) break;
    out = next;
  }
  return out;
}

export function Table(props: {
  rows?: ScreenerRow[] | null;          // <-- allow undefined/null safely
  onRowClick: (row: ScreenerRow) => void;
}) {
  const safeRows: ScreenerRow[] = Array.isArray(props.rows) ? props.rows : [];
  const { onRowClick } = props;

  return (
    <div style={{ width: "100%" }}>
      <table style={styles.table}>
        <thead>
          <tr>
            {[
              "Symbol",
              "Description",
              "Last",
              "%Change",
              "Shortable",
              "MktCap",
              "Float",
              "Trades/Min",
              "Vol/Min",
              "Volume",
              "Latest News (UTC)",
              "Latest Headline",
              "News",
            ].map((h) => (
              <th key={h} style={styles.th}>
                {h}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {safeRows.length === 0 ? (
            <tr>
              <td style={styles.empty} colSpan={13}>
                No rows to display.
              </td>
            </tr>
          ) : (
            safeRows.map((r) => (
              <tr key={r.symbol} style={styles.tr} onClick={() => onRowClick(r)}>
                <td style={styles.tdSymbol}>{r.symbol}</td>
                <td style={styles.tdDesc} title={cell(r.description)}>
                  {cell(r.description)}
                </td>
                <td style={styles.td}>{cell(r.last)}</td>
                <td style={styles.td}>{cell(r.pctChange)}</td>
                <td style={styles.td}>{cell(r.shortableShares)}</td>
                <td style={styles.td}>{cell(r.marketCap)}</td>
                <td style={styles.td}>{cell(r.floatShares)}</td>
                <td style={styles.td}>{cell(r.tradesPerMin)}</td>
                <td style={styles.td}>{cell(r.volumePerMin)}</td>
                <td style={styles.td}>{cell(r.volume)}</td>
                <td style={styles.tdMono}>{cell(r.latestNewsUtc)}</td>
                <td style={styles.tdHeadline} title={cleanHeadline(r.latestHeadline)}>
                  {cleanHeadline(r.latestHeadline)}
                </td>
                <td style={styles.td}>{cell(r.newsCount)}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      <div style={{ height: 16 }} />
      <div style={{ opacity: 0.6, fontSize: 12 }}>
        Tip: click a row to view all headlines for that symbol.
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  table: {
    width: "100%",
    borderCollapse: "separate",
    borderSpacing: 0,
    background: "white",
    border: "1px solid #e5e7eb",
    borderRadius: 14,
    overflow: "hidden",
  },
  th: {
    position: "sticky",
    top: 0,
    background: "#f8fafc",
    textAlign: "left",
    fontSize: 12,
    padding: "10px 10px",
    borderBottom: "1px solid #e5e7eb",
    whiteSpace: "nowrap",
    zIndex: 1,
  },
  tr: { cursor: "pointer" },
  td: {
    padding: "10px 10px",
    borderBottom: "1px solid #f1f5f9",
    fontSize: 13,
    whiteSpace: "nowrap",
  },
  tdMono: {
    padding: "10px 10px",
    borderBottom: "1px solid #f1f5f9",
    fontSize: 12,
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    whiteSpace: "nowrap",
  },
  tdSymbol: {
    padding: "10px 10px",
    borderBottom: "1px solid #f1f5f9",
    fontSize: 13,
    fontWeight: 800,
    whiteSpace: "nowrap",
  },
  tdDesc: {
    padding: "10px 10px",
    borderBottom: "1px solid #f1f5f9",
    fontSize: 13,
    maxWidth: 260,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  tdHeadline: {
    padding: "10px 10px",
    borderBottom: "1px solid #f1f5f9",
    fontSize: 13,
    maxWidth: 520,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  empty: {
    padding: "14px 10px",
    fontSize: 13,
    opacity: 0.7,
  },
};
