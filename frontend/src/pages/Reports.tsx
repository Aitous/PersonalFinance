import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import {
  getMonthlyReport, generateNarrative,
  MonthlyReport,
} from "../api/reports";

interface StatCard {
  label: string;
  value: string;
  valueColor?: string;
  sub?: string;
}

interface CategoryRow {
  name: string;
  current: number;
  prior: number;
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

  useEffect(() => {
    setLoading(true);
    setError(null);
    getMonthlyReport(year, month)
      .then(setReport)
      .catch(() => setError("Failed to load report."))
      .finally(() => setLoading(false));
  }, [year, month]);

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

  const card: React.CSSProperties = {
    background: "#1e1b4b", borderRadius: 12, padding: "20px 24px", marginBottom: 20,
  };
  const label: React.CSSProperties = { fontSize: 12, color: "#9ca3af", marginBottom: 4 };
  const sectionTitle: React.CSSProperties = {
    fontSize: 13, fontWeight: 700, color: "#a5b4fc", letterSpacing: "0.05em",
    textTransform: "uppercase", marginBottom: 14,
  };

  return (
    <div style={{ maxWidth: 860, margin: "0 auto", padding: "32px 24px", color: "#e0e7ff" }}>
      {/* Header + month picker */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 28 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: "#fff", margin: 0 }}>Monthly Report</h1>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            onClick={() => stepMonth(-1)}
            style={{ background: "#312e81", border: "none", color: "#c4b5fd", borderRadius: 8, padding: "6px 14px", cursor: "pointer", fontSize: 16 }}
          >◀</button>
          <span style={{ fontWeight: 600, fontSize: 16, minWidth: 140, textAlign: "center" }}>
            {MONTH_NAMES[month]} {year}
          </span>
          <button
            onClick={() => stepMonth(1)}
            style={{ background: "#312e81", border: "none", color: "#c4b5fd", borderRadius: 8, padding: "6px 14px", cursor: "pointer", fontSize: 16 }}
          >▶</button>
        </div>
      </div>

      {loading && <div style={{ color: "#9ca3af", textAlign: "center", padding: 60 }}>Loading...</div>}
      {error && <div style={{ color: "#f87171", textAlign: "center", padding: 60 }}>{error}</div>}

      {report && !loading && (
        <>
          {/* 1. AI Narrative */}
          <div style={card}>
            <div style={sectionTitle}>Summary</div>
            {report.narrative ? (
              <p style={{ margin: 0, lineHeight: 1.7, color: "#e0e7ff" }}>{report.narrative}</p>
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
          <div style={{ display: "flex", gap: 16, marginBottom: 20 }}>
            {([
              { label: "Total spent", value: fmt(report.total) },
              {
                label: "vs last month",
                value: pctChange(report.total, report.prev_total) ?? "—",
                valueColor: report.total <= report.prev_total ? "#6ee7b7" : "#f87171",
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
              <div style={sectionTitle}>Spending by Category</div>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart
                  data={report.categories}
                  layout="vertical"
                  margin={{ left: 80, right: 30, top: 4, bottom: 4 }}
                  onClick={(data) => {
                    if (!data?.activePayload) return;
                    const cat = (data.activePayload[0]?.payload as CategoryRow)?.name;
                    if (!cat) return;
                    const pad = (n: number) => String(n).padStart(2, "0");
                    const from = `${year}-${pad(month)}-01`;
                    const lastDay = new Date(year, month, 0).getDate();
                    const to = `${year}-${pad(month)}-${pad(lastDay)}`;
                    navigate(`/transactions?category=${encodeURIComponent(cat)}&dateFrom=${from}&dateTo=${to}`);
                  }}
                  style={{ cursor: "pointer" }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#312e81" horizontal={false} />
                  <XAxis type="number" tick={{ fill: "#9ca3af", fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" tick={{ fill: "#e0e7ff", fontSize: 12 }} width={76} />
                  <Tooltip
                    contentStyle={{ background: "#1e1b4b", border: "1px solid #312e81", borderRadius: 8 }}
                    labelStyle={{ color: "#c4b5fd" }}
                    itemStyle={{ color: "#e0e7ff" }}
                    formatter={(v: number) => fmt(v)}
                  />
                  <Legend wrapperStyle={{ color: "#9ca3af", fontSize: 12 }} />
                  <Bar dataKey="current" name={`${MONTH_NAMES[month]}`} fill="#7c6af7" radius={[0, 3, 3, 0]} />
                  <Bar dataKey="prior" name="Prior month" fill="#c4b5fd" radius={[0, 3, 3, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* 4. Top merchants */}
          {report.merchants.length > 0 && (
            <div style={card}>
              <div style={sectionTitle}>Top Merchants</div>
              {report.merchants.map((m, i) => {
                const pad = (n: number) => String(n).padStart(2, "0");
                const from = `${year}-${pad(month)}-01`;
                const lastDay = new Date(year, month, 0).getDate();
                const to = `${year}-${pad(month)}-${pad(lastDay)}`;
                return (
                  <div
                    key={m.name}
                    onClick={() => navigate(`/transactions?search=${encodeURIComponent(m.name)}&dateFrom=${from}&dateTo=${to}`)}
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
                      <span style={{ color: "#e0e7ff" }}>{m.name}</span>
                    </div>
                    <span style={{ color: "#c4b5fd", fontWeight: 600 }}>{fmt(m.total)}</span>
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
                    <span style={{ color: "#fde68a", marginRight: 8 }}>⚠</span>
                    <span style={{ color: "#e0e7ff" }}>{s.description}</span>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ color: "#c4b5fd", fontWeight: 600 }}>{fmt(s.amount)}</div>
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
