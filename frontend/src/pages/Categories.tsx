import { useEffect, useState } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { getCategorySummary } from "../api/client";

const COLORS = ["#7c6af7","#a78bfa","#c4b5fd","#60a5fa","#34d399","#f59e0b","#f87171","#38bdf8","#94a3b8","#d1d5db"];

export function Categories() {
  const [summary, setSummary] = useState<Record<string, any>>({});

  useEffect(() => { getCategorySummary().then(setSummary); }, []);

  const pieData = Object.entries(summary).map(([name, d]) => ({ name, value: d.total }));

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 8 }}>Categories</h1>
      <p style={{ color: "#888", marginBottom: 24 }}>Last 3 months of spending by category</p>

      <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
        <div style={{ background: "#fff", borderRadius: 10, padding: 24, boxShadow: "0 1px 4px rgba(0,0,0,0.07)", flex: "1 1 360px" }}>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={110} label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}>
                {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip formatter={(v) => typeof v === "number" ? `$${v.toFixed(2)}` : v} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div style={{ flex: "1 1 280px" }}>
          {Object.entries(summary).sort((a, b) => b[1].total - a[1].total).map(([cat, d], i) => (
            <div key={cat} style={{ background: "#fff", borderRadius: 8, padding: "12px 16px", marginBottom: 10, boxShadow: "0 1px 3px rgba(0,0,0,0.06)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 12, height: 12, borderRadius: "50%", background: COLORS[i % COLORS.length] }} />
                <span style={{ textTransform: "capitalize", fontSize: 14 }}>{cat}</span>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontWeight: 700, fontSize: 15 }}>${d.total.toFixed(2)}</div>
                <div style={{ color: "#888", fontSize: 12 }}>${d.avg_monthly.toFixed(2)}/mo</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
