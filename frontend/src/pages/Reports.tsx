import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { getMonthlyReport, generateNarrative } from "../api/reports";
import type { MonthlyReport } from "../api/reports";
import { transactionFiltersUrl } from "../api/transactionFilters";
import { reportPeriodRange } from "../api/reliabilityHelpers";

interface StatCard {
  label: string;
  value: string;
  valueColor?: string;
  sub?: string;
}

function lastCompleteMonth(): { year: number; month: number } {
  const today = new Date();
  const month = today.getMonth(); // 0-indexed, so this is "previous month" in 1-indexed
  const year = month === 0 ? today.getFullYear() - 1 : today.getFullYear();
  return { year, month: month === 0 ? 12 : month };
}

const MONTH_NAMES = [
  "", "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function pctChange(current: number, prior: number): string | null {
  if (prior === 0) return null;
  const pct = ((current - prior) / prior) * 100;
  return (pct > 0 ? "+" : "") + pct.toFixed(1) + "%";
}

function fmt(n: number): string {
  return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

export default function Reports() {
  const navigate = useNavigate();
  const initial = lastCompleteMonth();
  const [year, setYear] = useState(initial.year);
  const [month, setMonth] = useState(initial.month);
  const [report, setReport] = useState<MonthlyReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [narrativeLoading, setNarrativeLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getMonthlyReport(year, month)
      .then(setReport)
      .catch(() => setError("Failed to load report."))
      .finally(() => setLoading(false));
  }, [year, month, reloadToken]);

  function stepMonth(delta: number) {
    let m = month + delta;
    let y = year;
    if (m < 1) { m = 12; y -= 1; }
    if (m > 12) { m = 1; y += 1; }
    setYear(y);
    setMonth(m);
  }

  async function handleGenerateNarrative() {
    if (!report) return;
    setNarrativeLoading(true);
    try {
      const narrative = await generateNarrative(year, month);
      setReport({ ...report, narrative });
    } catch {
      setError("Failed to generate summary.");
    } finally {
      setNarrativeLoading(false);
    }
  }

  function openCategoryPeriod(category: string, series: "current" | "prior") {
    const range = reportPeriodRange(year, month, series);
    if (range) navigate(transactionFiltersUrl({ category, ...range }));
  }

  const priorMonth = month === 1 ? 12 : month - 1;
  const priorYear = month === 1 ? year - 1 : year;

  const card: React.CSSProperties = {
    background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12, padding: "20px 24px", marginBottom: 20,
  };
  const label: React.CSSProperties = { fontSize: 12, color: "#9ca3af", marginBottom: 4 };
  const sectionTitle: React.CSSProperties = {
    fontSize: 13, fontWeight: 700, color: "#6d5bd0", letterSpacing: "0.05em",
    textTransform: "uppercase", marginBottom: 14,
  };

  return (
    <div style={{ maxWidth: 1000, margin: "0 auto", padding: "24px 0", color: "#1f2937" }}>
      {/* Header + month picker */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 28 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: "#111827", margin: 0 }}>Monthly Report</h1>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            onClick={() => stepMonth(-1)}
            aria-label="Previous month" style={{ background: "#fff", border: "1px solid #d1d5db", color: "#4b5563", borderRadius: 8, padding: "6px 14px", cursor: "pointer", fontSize: 16 }}
          >◀</button>
          <span style={{ fontWeight: 600, fontSize: 16, minWidth: 140, textAlign: "center" }}>
            {MONTH_NAMES[month]} {year}
          </span>
          <button
            onClick={() => stepMonth(1)}
            aria-label="Next month" style={{ background: "#fff", border: "1px solid #d1d5db", color: "#4b5563", borderRadius: 8, padding: "6px 14px", cursor: "pointer", fontSize: 16 }}
          >▶</button>
        </div>
      </div>

      {loading && <div style={{ color: "#9ca3af", textAlign: "center", padding: 60 }}>Loading...</div>}
      {error && <div role="alert" style={{ color: "#b91c1c", textAlign: "center", padding: 40 }}>{error}<div><button onClick={() => setReloadToken((v) => v + 1)} style={{ marginTop: 10, border: "1px solid #ddd", borderRadius: 6, background: "#fff", padding: "7px 12px", cursor: "pointer" }}>Retry</button></div></div>}

      {report && !loading && (
        <>
          {/* 1. AI Narrative */}
          <div style={card}>
            <div style={sectionTitle}>Summary</div>
            {report.narrative ? (
              <p style={{ margin: 0, lineHeight: 1.7, color: "#374151" }}>{report.narrative}</p>
            ) : (
              <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                <p style={{ margin: 0, color: "#6b7280" }}>No summary generated yet.</p>
                <button
                  onClick={handleGenerateNarrative}
                  disabled={narrativeLoading}
                  style={{
                    background: "#7c6af7", border: "none", color: "#fff", borderRadius: 8,
                    padding: "8px 18px", cursor: narrativeLoading ? "default" : "pointer",
                    fontSize: 13, opacity: narrativeLoading ? 0.6 : 1,
                  }}
                >
                  {narrativeLoading ? "Generating…" : "Generate summary"}
                </button>
              </div>
            )}
          </div>

          {/* 2. Stats row */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 16, marginBottom: 20 }}>
            {([
              { label: "Gross purchases", value: fmt(report.gross_total ?? report.total) },
              { label: "Refunds", value: report.refund_total === undefined ? "Not provided" : fmt(report.refund_total) },
              { label: "Net spending", value: report.net_total === undefined ? "Not provided" : fmt(report.net_total) },
              {
                label: "Gross purchases vs last month",
                value: pctChange(report.total, report.prev_total) ?? "—",
                valueColor: report.total <= report.prev_total ? "#047857" : "#b91c1c",
                sub: report.prev_total > 0
                  ? `${report.total <= report.prev_total ? "−" : "+"}${fmt(Math.abs(report.total - report.prev_total))}`
                  : undefined,
              },
              { label: "Transactions", value: String(report.tx_count) },
            ] as StatCard[]).map((s) => (
              <div key={s.label} style={{ ...card, flex: 1, marginBottom: 0, textAlign: "center" }}>
                <div style={label}>{s.label}</div>
                <div style={{ fontSize: 26, fontWeight: 700, color: s.valueColor ?? "#fff" }}>{s.value}</div>
                {s.sub && <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 2 }}>{s.sub}</div>}
              </div>
            ))}
          </div>

          {/* 3. Category breakdown */}
          {report.categories.length > 0 && (
            <div style={card}>
              <div style={sectionTitle}>Gross Purchases by Category</div>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart
                  data={report.categories}
                  layout="vertical"
                  margin={{ left: 80, right: 30, top: 4, bottom: 4 }}
                  onClick={(data) => {
                    const cat = typeof data?.activeLabel === "string" ? data.activeLabel : "";
                    if (cat && (data.activeDataKey === "current" || data.activeDataKey === "prior")) {
                      openCategoryPeriod(cat, data.activeDataKey);
                    }
                  }}
                  style={{ cursor: "pointer" }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#312e81" horizontal={false} />
                  <XAxis type="number" tick={{ fill: "#9ca3af", fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" tick={{ fill: "#374151", fontSize: 12 }} width={76} />
                  <Tooltip
                    contentStyle={{ background: "#1e1b4b", border: "1px solid #312e81", borderRadius: 8 }}
                    labelStyle={{ color: "#374151" }}
                    itemStyle={{ color: "#374151" }}
                    formatter={(v) => fmt(Number(v ?? 0))}
                  />
                  <Legend wrapperStyle={{ color: "#9ca3af", fontSize: 12 }} />
                  <Bar dataKey="current" name={`${MONTH_NAMES[month]}`} fill="#7c6af7" radius={[0, 3, 3, 0]} />
                  <Bar dataKey="prior" name="Prior month" fill="#c4b5fd" radius={[0, 3, 3, 0]} />
                </BarChart>
              </ResponsiveContainer>
                <div aria-label="Keyboard-accessible category transaction links" style={{ borderTop: "1px solid #e5e7eb", paddingTop: 10, fontSize: 12 }}>
                  <div style={{ color: "#6b7280", marginBottom: 6 }}>Open category transactions by period:</div>
                  {report.categories.map((category) => (
                    <div key={category.name} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap", padding: "4px 0" }}>
                      <span>{category.name}</span>
                      <div style={{ display: "flex", gap: 6 }}>
                        <button onClick={() => openCategoryPeriod(category.name, "current")} aria-label={`Open ${category.name} transactions for ${MONTH_NAMES[month]} ${year}`} style={{ border: "1px solid #d1d5db", borderRadius: 5, background: "#fff", padding: "4px 8px", cursor: "pointer" }}>{MONTH_NAMES[month]} {year}</button>
                        <button onClick={() => openCategoryPeriod(category.name, "prior")} aria-label={`Open ${category.name} transactions for ${MONTH_NAMES[priorMonth]} ${priorYear}`} style={{ border: "1px solid #d1d5db", borderRadius: 5, background: "#fff", padding: "4px 8px", cursor: "pointer" }}>{MONTH_NAMES[priorMonth]} {priorYear}</button>
                      </div>
                    </div>
                  ))}
                </div>
            </div>
          )}

          {/* 4. Top merchants */}
          {report.merchants.length > 0 && (
            <div style={card}>
              <div style={sectionTitle}>Top Merchants by Gross Purchases</div>
              {report.merchants.map((m, i) => {
                const pad = (n: number) => String(n).padStart(2, "0");
                const from = `${year}-${pad(month)}-01`;
                const lastDay = new Date(year, month, 0).getDate();
                const to = `${year}-${pad(month)}-${pad(lastDay)}`;
                return (
                  <div
                    key={m.name}
                    onClick={() => navigate(transactionFiltersUrl({ merchant: m.name, date_from: from, date_to: to }))}
                    style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "10px 0", borderBottom: i < report.merchants.length - 1 ? "1px solid #312e81" : "none",
                      cursor: "pointer",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.opacity = "0.75")}
                    onMouseLeave={(e) => (e.currentTarget.style.opacity = "1")}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <span style={{ fontSize: 12, color: "#6b7280", minWidth: 18 }}>{i + 1}</span>
                      <span style={{ color: "#374151" }}>{m.name}</span>
                    </div>
                    <span style={{ color: "#5b4bb7", fontWeight: 600 }}>{fmt(m.total)}</span>
                  </div>
                );
              })}
            </div>
          )}

          {/* 5. Subscriptions due */}
          {report.subscriptions_due.length > 0 && (
            <div style={card}>
              <div style={sectionTitle}>Subscriptions Renewing Soon</div>
              {report.subscriptions_due.map((s, i) => (
                <div
                  key={s.description + s.next_date}
                  onClick={() => navigate("/subscriptions")}
                  style={{
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    padding: "10px 0",
                    borderBottom: i < report.subscriptions_due.length - 1 ? "1px solid #312e81" : "none",
                    cursor: "pointer",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.opacity = "0.75")}
                  onMouseLeave={(e) => (e.currentTarget.style.opacity = "1")}
                >
                  <div>
                    <span style={{ color: "#92400e", marginRight: 8 }}>⚠</span>
                    <span style={{ color: "#374151" }}>{s.description}</span>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ color: "#5b4bb7", fontWeight: 600 }}>{fmt(s.amount)}</div>
                    <div style={{ fontSize: 11, color: "#6b7280" }}>{s.next_date}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
