import { useEffect, useState } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { getCategorySummary } from "../api/client";

const COLORS = ["#7c6af7","#a78bfa","#60a5fa","#34d399","#f59e0b","#fb923c","#f87171","#38bdf8","#94a3b8","#6b7280"];

const RANGES = [
  { label: "Last 30 days", days: 30 },
  { label: "Last 3 months", days: 90 },
  { label: "Last 6 months", days: 180 },
  { label: "Last 12 months", days: 365 },
];

export function Categories() {
  const [summary, setSummary] = useState<Record<string, any>>({});
  const [days, setDays] = useState(90);
  const [chartHeight, setChartHeight] = useState(400);

  useEffect(() => { getCategorySummary(days).then(setSummary); }, [days]);

  const pieData = Object.entries(summary)
    .map(([name, d]) => ({ name, value: d.total }))
    .sort((a, b) => b.value - a.value);

  const rangeLabel = RANGES.find((r) => r.days === days)?.label ?? `Last ${days} days`;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <h1 style={{ fontSize: 24, margin: 0 }}>Categories</h1>
        <div style={{ display: "flex", gap: 6 }}>
          {RANGES.map((r) => (
            <button key={r.days} onClick={() => setDays(r.days)} style={{
              padding: "6px 12px", borderRadius: 20, fontSize: 12, cursor: "pointer", border: "none",
              background: days === r.days ? "#7c6af7" : "rgba(124,106,247,0.12)",
              color: days === r.days ? "#fff" : "#7c6af7",
              fontWeight: days === r.days ? 600 : 400,
            }}>
              {r.label}
            </button>
          ))}
        </div>
      </div>
      <p style={{ color: "#888", marginBottom: 24, fontSize: 14 }}>{rangeLabel} of spending by category</p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <div style={{ background: "#fff", borderRadius: 10, padding: 24, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, justifyContent: "flex-end" }}>
            <span style={{ fontSize: 12, color: "#9ca3af" }}>Size</span>
            <input type="range" min={240} max={700} step={20} value={chartHeight}
              onChange={(e) => setChartHeight(Number(e.target.value))}
              style={{ width: 100, accentColor: "#7c6af7" }} />
          </div>
          <ResponsiveContainer width="100%" height={chartHeight}>
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius="42%"
                label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                labelLine={{ stroke: "#9ca3af" }}
              >
                {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip
                contentStyle={{ background: "#1e1b4b", border: "1px solid #4c1d95", borderRadius: 8, color: "#e0e7ff" }}
                formatter={(v) => typeof v === "number" ? `$${v.toFixed(2)}` : v}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div>
          {pieData.map(({ name }, i) => {
            const d = summary[name];
            return (
              <div key={name} style={{ background: "#fff", borderRadius: 8, padding: "12px 16px", marginBottom: 10, boxShadow: "0 1px 3px rgba(0,0,0,0.06)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{ width: 12, height: 12, borderRadius: "50%", background: COLORS[i % COLORS.length] }} />
                  <span style={{ textTransform: "capitalize", fontSize: 14 }}>{name}</span>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontWeight: 700, fontSize: 15 }}>${d.total.toFixed(2)}</div>
                  <div style={{ color: "#888", fontSize: 12 }}>${d.avg_monthly.toFixed(2)}/mo · {d.count} txs</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
