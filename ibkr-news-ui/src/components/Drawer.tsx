import React from "react";
import type { HeadlineItem } from "../types";

export function Drawer(props: {
  open: boolean;
  title: string;
  onClose: () => void;
  loading?: boolean;
  error?: string | null;
  items: HeadlineItem[];
}) {
  const { open, title, onClose, loading, error, items } = props;
  if (!open) return null;

  return (
    <div style={styles.backdrop} onMouseDown={onClose}>
      <div style={styles.panel} onMouseDown={(e) => e.stopPropagation()}>
        <div style={styles.header}>
          <div>
            <div style={{ fontWeight: 800, fontSize: 16 }}>{title}</div>
            <div style={{ fontSize: 12, opacity: 0.7, marginTop: 2 }}>
              Click outside to close
            </div>
          </div>
          <button onClick={onClose} style={styles.closeBtn}>✕</button>
        </div>

        <div style={styles.body}>
          {loading && <div style={styles.muted}>Loading headlines…</div>}
          {error && <div style={styles.error}>{error}</div>}
          {!loading && !error && items.length === 0 && (
            <div style={styles.muted}>No headlines in this window.</div>
          )}

          {!loading && !error && items.length > 0 && (
            <div style={{ display: "grid", gap: 10 }}>
              {items.map((it, idx) => (
                <div key={`${it.articleId ?? idx}-${idx}`} style={styles.card}>
                  <div style={styles.cardTop}>
                    <span style={styles.badge}>{it.provider}</span>
                    <span style={styles.meta}>{it.publishedUtc} UTC</span>
                  </div>
                  <div style={styles.headline}>{it.headline}</div>
                  <div style={styles.meta2}>
                    {it.providerName}{it.articleId ? ` • ${it.articleId}` : ""}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  backdrop: {
    position: "fixed",
    inset: 0,
    background: "rgba(0,0,0,0.35)",
    display: "flex",
    justifyContent: "flex-end",
    zIndex: 50,
  },
  panel: {
    width: 520,
    maxWidth: "92vw",
    height: "100vh",
    background: "white",
    boxShadow: "-10px 0 30px rgba(0,0,0,0.2)",
    display: "flex",
    flexDirection: "column",
  },
  header: {
    padding: 14,
    borderBottom: "1px solid #e5e7eb",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
  },
  closeBtn: {
    border: "1px solid #d1d5db",
    background: "white",
    borderRadius: 10,
    padding: "8px 10px",
    cursor: "pointer",
    fontWeight: 700,
  },
  body: {
    padding: 14,
    overflow: "auto", // drawer scroll is fine; main page still uses browser scroll for table
  },
  muted: { opacity: 0.7 },
  error: { color: "#b91c1c", fontWeight: 700 },
  card: {
    border: "1px solid #e5e7eb",
    borderRadius: 14,
    padding: 12,
  },
  cardTop: { display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" },
  badge: {
    fontSize: 12,
    border: "1px solid #e5e7eb",
    padding: "2px 8px",
    borderRadius: 999,
    fontWeight: 700,
    background: "#f8fafc",
  },
  meta: { fontSize: 12, opacity: 0.7 },
  headline: { marginTop: 8, fontWeight: 700, lineHeight: 1.3 },
  meta2: { marginTop: 6, fontSize: 12, opacity: 0.7 },
};
