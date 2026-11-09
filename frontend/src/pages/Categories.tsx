import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { getCategorySummary } from "../api/client";
import { transactionFiltersUrl } from "../api/transactionFilters";
import { useSpendingRange } from "../components/spendingRange";

const COLORS = ["#287c61","#9bc68b","#d6a967","#648e92","#d47e6e","#8a8fb5","#b4b883","#70aab0","#c397aa","#778980"];

export function Categories() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<Record<string, any>>({});
  const { days, customRange } = useSpendingRange();
  const [chartHeight, setChartHeight] = useState(580);

  useEffect(() => { getCategorySummary(days, customRange ?? undefined).then(setSummary); }, [days, customRange]);

  const pieData = Object.entries(summary)
    .map(([name, d]) => ({ name, value: d.total }))
    .sort((a, b) => b.value - a.value);

  const rangeLabel = customRange ? `${customRange.from} – ${customRange.to}` : `Last ${days} days`;

  const openCategory = (category: string) => {
    const from = customRange ? new Date(`${customRange.from}T00:00:00`) : new Date();
    if (!customRange) from.setDate(from.getDate() - days);
    const to = customRange ? new Date(`${customRange.to}T00:00:00`) : new Date();
    const formatDate = (date: Date) => {
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, "0");
      const day = String(date.getDate()).padStart(2, "0");
      return `${year}-${month}-${day}`;
    };
    navigate(transactionFiltersUrl({ category, date_from: formatDate(from), date_to: formatDate(to) }));
  };

  return (
    <div id="spending-categories" className="spending-analysis-section">
      <div className="categories-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <h2 style={{ fontSize: 20, margin: 0 }}>By category</h2>
      </div>
      <p style={{ color: "#888", marginBottom: 24, fontSize: 14 }}>{rangeLabel} of spending by category</p>

      <div className="categories-content" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <div style={{ background: "#fff", borderRadius: 10, padding: 24, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, justifyContent: "flex-end" }}>
            <span style={{ fontSize: 12, color: "#9ca3af" }}>Size</span>
            <input aria-label="Chart size" type="range" min={240} max={700} step={20} value={chartHeight}
              onChange={(e) => setChartHeight(Number(e.target.value))}
              style={{ width: 100, accentColor: "#276c54" }} />
          </div>
          <ResponsiveContainer width="100%" height={chartHeight}>
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius="45%"
                label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                labelLine={{ stroke: "#9ca3af" }}
              >
                {pieData.map(({ name }, i) => <Cell key={name} fill={COLORS[i % COLORS.length]} cursor="pointer" onClick={() => openCategory(name)} />)}
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
              <button key={name} type="button" className="category-drilldown-row" aria-label={`View ${d.count} ${name} transactions from ${rangeLabel}`} onClick={() => openCategory(name)} style={{ background: "#fff", borderRadius: 8, padding: "12px 16px", marginBottom: 10, boxShadow: "0 1px 3px rgba(0,0,0,0.06)", display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%", border: "1px solid #e5e7eb", textAlign: "left" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{ width: 12, height: 12, borderRadius: "50%", background: COLORS[i % COLORS.length] }} />
                  <span style={{ textTransform: "capitalize", fontSize: 14 }}>{name}</span>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontWeight: 700, fontSize: 15 }}>${d.total.toFixed(2)}</div>
                  <div style={{ color: "#888", fontSize: 12 }}>${d.avg_monthly.toFixed(2)}/mo · {d.count} txs</div>
                  <div className="category-drilldown-hint">View transactions <span aria-hidden="true">↗</span></div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
