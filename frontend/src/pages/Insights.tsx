import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getInsights } from "../api/client";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LabelList } from "recharts";

const SECTION = {
  background: "#fff", borderRadius: 10, padding: 24,
  boxShadow: "0 1px 4px rgba(0,0,0,0.07)", marginBottom: 24,
};

const CATEGORY_COLORS: Record<string, string> = {
  dining: "#7c6af7", groceries: "#a78bfa", transport: "#c4b5fd",
  shopping: "#60a5fa", entertainment: "#34d399", subscriptions: "#f59e0b",
  health: "#f87171", travel: "#38bdf8", utilities: "#94a3b8", other: "#d1d5db",
};

export function Insights() {
  const navigate = useNavigate();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [merchantDays, setMerchantDays] = useState(90);
  const [merchantSearch, setMerchantSearch] = useState("");
  const [avgMonths, setAvgMonths] = useState<3 | 6 | 12>(3);
  const [avgDateFrom, setAvgDateFrom] = useState("");
  const [avgDateTo, setAvgDateTo] = useState("");
  const [avgData, setAvgData] = useState<any>(null);
  const [avgLoading, setAvgLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    getInsights(merchantDays)
      .then(setData)
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false));
  }, [merchantDays]);

  useEffect(() => {
    setAvgLoading(true);
    const params = avgDateFrom && avgDateTo
      ? `date_from=${avgDateFrom}&date_to=${avgDateTo}`
      : `months=${avgMonths}`;
    fetch(`http://localhost:8000/analysis/monthly-averages?${params}`)
      .then((r) => r.json())
      .then(setAvgData)
      .finally(() => setAvgLoading(false));
  }, [avgMonths, avgDateFrom, avgDateTo]);

  if (loading) return <p>Loading insights…</p>;
  if (error) return <p style={{ color: "red" }}>Failed to load insights: {error}</p>;
  if (!data) return null;

  const { alerts, merchants, day_of_week, year_over_year } = data;
  const totalAlerts = alerts.anomalies.length + alerts.duplicates.length + alerts.price_increases.length;

  const filteredMerchants = merchants.filter((m: any) =>
    m.name.toLowerCase().includes(merchantSearch.toLowerCase())
  );

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 24 }}>Insights</h1>

      {/* ── Alerts ── */}
      <div style={SECTION}>
        <h2 style={{ margin: "0 0 16px", fontSize: 16 }}>⚡ Alerts</h2>
        {totalAlerts === 0 ? (
          <div style={{ background: "#d1fae5", borderLeft: "3px solid #10b981", padding: "10px 14px", borderRadius: 6 }}>
            <span style={{ color: "#065f46", fontWeight: 600 }}>✓ All clear — no anomalies detected this month.</span>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {alerts.anomalies.map((a: any) => (
              <div key={a.category} onClick={() => navigate(`/transactions?ids=${encodeURIComponent(a.tx_ids.join(","))}`)}
                style={{ background: "#fef3c7", borderLeft: "3px solid #f59e0b", padding: "10px 14px", borderRadius: 6, cursor: "pointer" }}
                onMouseEnter={(e) => (e.currentTarget.style.opacity = "0.8")}
                onMouseLeave={(e) => (e.currentTarget.style.opacity = "1")}>
                <div style={{ fontWeight: 600, color: "#92400e" }}>
                  ⚠ {a.category.charAt(0).toUpperCase() + a.category.slice(1)} spend is {a.ratio}× your 3-month average
                </div>
                <div style={{ color: "#78350f", marginTop: 2, fontSize: 13, display: "flex", justifyContent: "space-between" }}>
                  <span>${a.current_amount.toFixed(2)} this month vs. ${a.avg_amount.toFixed(2)} avg — {a.tx_count} transactions</span>
                  <span style={{ fontSize: 11, opacity: 0.7 }}>View transactions →</span>
                </div>
              </div>
            ))}
            {alerts.duplicates.map((d: any, i: number) => (
              <div key={i} onClick={() => navigate(`/transactions?ids=${encodeURIComponent(d.tx_ids.join(","))}`)}
                style={{ background: "#fee2e2", borderLeft: "3px solid #ef4444", padding: "10px 14px", borderRadius: 6, cursor: "pointer" }}
                onMouseEnter={(e) => (e.currentTarget.style.opacity = "0.8")}
                onMouseLeave={(e) => (e.currentTarget.style.opacity = "1")}>
                <div style={{ fontWeight: 600, color: "#991b1b" }}>
                  🔁 Possible duplicate: {d.merchant}
                </div>
                <div style={{ color: "#7f1d1d", marginTop: 2, fontSize: 13, display: "flex", justifyContent: "space-between" }}>
                  <span>${d.amount.toFixed(2)} charged {d.dates.length} times ({d.dates.join(" & ")})</span>
                  <span style={{ fontSize: 11, opacity: 0.7 }}>View transactions →</span>
                </div>
              </div>
            ))}
            {alerts.price_increases.map((p: any, i: number) => (
              <div key={i} onClick={() => navigate(`/transactions?ids=${encodeURIComponent(p.tx_ids.join(","))}`)}
                style={{ background: "#ede9fe", borderLeft: "3px solid #7c3aed", padding: "10px 14px", borderRadius: 6, cursor: "pointer" }}
                onMouseEnter={(e) => (e.currentTarget.style.opacity = "0.8")}
                onMouseLeave={(e) => (e.currentTarget.style.opacity = "1")}>
                <div style={{ fontWeight: 600, color: "#4c1d95" }}>
                  📈 Price increase: {p.merchant}
                </div>
                <div style={{ color: "#3b0764", marginTop: 2, fontSize: 13, display: "flex", justifyContent: "space-between" }}>
                  <span>${p.old_amount.toFixed(2)} → ${p.new_amount.toFixed(2)} starting {p.first_new_date} (+${p.delta.toFixed(2)}/charge)</span>
                  <span style={{ fontSize: 11, opacity: 0.7 }}>View transactions →</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Merchant Breakdown ── */}
      <div style={SECTION}>
        <h2 style={{ margin: "0 0 16px", fontSize: 16 }}>🏪 Merchant Breakdown</h2>
        <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center" }}>
          <input
            value={merchantSearch}
            onChange={(e) => setMerchantSearch(e.target.value)}
            placeholder="Search merchants…"
            style={{ flex: 1, padding: "7px 12px", borderRadius: 6, border: "1.5px solid #e5e7eb", fontSize: 13 }}
          />
          <select
            value={merchantDays}
            onChange={(e) => setMerchantDays(Number(e.target.value))}
            style={{ padding: "7px 10px", borderRadius: 6, border: "1px solid #ddd", fontSize: 13 }}
          >
            <option value={90}>Last 90 days</option>
            <option value={180}>Last 6 months</option>
            <option value={730}>All time</option>
          </select>
        </div>
        <div style={{ borderRadius: 8, overflow: "hidden", border: "1px solid #f0f0f0" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#f9fafb", textAlign: "left" }}>
                <th style={{ padding: "10px 16px", fontWeight: 600, color: "#6b7280" }}>Merchant</th>
                <th style={{ padding: "10px 16px", fontWeight: 600, color: "#6b7280" }}>Category</th>
                <th style={{ padding: "10px 16px", fontWeight: 600, color: "#6b7280" }}>City</th>
                <th style={{ padding: "10px 16px", fontWeight: 600, color: "#6b7280", textAlign: "right" }}>Txns</th>
                <th style={{ padding: "10px 16px", fontWeight: 600, color: "#6b7280", textAlign: "right" }}>Total</th>
                <th style={{ padding: "10px 16px", width: 120 }}></th>
              </tr>
            </thead>
            <tbody>
              {filteredMerchants.map((m: any) => {
                const maxTotal = merchants[0]?.total ?? 1;
                const barWidth = Math.round((m.total / maxTotal) * 100);
                return (
                  <tr
                    key={m.name}
                    style={{ borderTop: "1px solid #f0f0f0", cursor: "pointer" }}
                    onClick={() => navigate(`/transactions?merchant=${encodeURIComponent(m.name)}`)}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "#f9fafb")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "")}
                  >
                    <td style={{ padding: "9px 16px", fontWeight: 500 }}>{m.name}</td>
                    <td style={{ padding: "9px 16px" }}>
                      <span style={{
                        background: CATEGORY_COLORS[m.category] ?? "#d1d5db",
                        color: "#fff", padding: "2px 8px", borderRadius: 12, fontSize: 11,
                      }}>{m.category}</span>
                    </td>
                    <td style={{ padding: "9px 16px", color: "#9ca3af", fontSize: 12 }}>{m.city ?? "—"}</td>
                    <td style={{ padding: "9px 16px", textAlign: "right", color: "#9ca3af" }}>{m.tx_count}</td>
                    <td style={{ padding: "9px 16px", textAlign: "right", fontWeight: 600 }}>${m.total.toFixed(2)}</td>
                    <td style={{ padding: "9px 16px" }}>
                      <div style={{ background: "#e5e7eb", borderRadius: 3, height: 6 }}>
                        <div style={{ width: `${barWidth}%`, background: "#7c6af7", borderRadius: 3, height: 6 }} />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {filteredMerchants.length === 0 && (
            <p style={{ textAlign: "center", color: "#9ca3af", padding: 24 }}>No merchants match your search.</p>
          )}
        </div>
        <div style={{ color: "#9ca3af", fontSize: 12, marginTop: 8 }}>
          Showing {filteredMerchants.length} of {merchants.length} merchants — click a row to see transactions
        </div>
      </div>

      {/* ── Day of Week ── */}
      <div style={SECTION}>
        <h2 style={{ margin: "0 0 16px", fontSize: 16 }}>📅 Spending by Day of Week</h2>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={day_of_week.days} margin={{ top: 20, right: 8, bottom: 4, left: 48 }}>
            <XAxis dataKey="day_name" tick={{ fontSize: 12 }} tickFormatter={(v: string) => v.slice(0, 3)} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => `$${(v / 1000).toFixed(1)}k`} width={60} />
            <Bar dataKey="total" radius={[4, 4, 0, 0]}
              label={{ position: "top", fontSize: 11, fill: "#6b7280", formatter: (v: number) => `$${(v / 1000).toFixed(1)}k` }}>
              {day_of_week.days.map((d: any) => (
                <Cell key={d.day} fill={d.day >= 5 ? "#f59e0b" : "#7c6af7"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p style={{ color: "#6b7280", fontSize: 13, margin: "8px 0 0" }}>
          Weekends (Sat–Sun) account for <strong>{day_of_week.weekend_pct}%</strong> of your spending.
        </p>
      </div>

      {/* ── Year over Year ── */}
      {!year_over_year.insufficient_data && (() => {
        const allCats = new Set<string>();
        year_over_year.years.forEach((y: any) =>
          Object.keys(y.categories).forEach((c: string) => allCats.add(c))
        );
        const cats = Array.from(allCats).filter((c) => c !== "other");
        const chartData = cats.map((cat) => {
          const entry: Record<string, any> = { category: cat.slice(0, 10) };
          year_over_year.years.forEach((y: any) => { entry[String(y.year)] = y.categories[cat] ?? 0; });
          return entry;
        }).sort((a, b) => {
          const lastYear = String(year_over_year.years[year_over_year.years.length - 1].year);
          return (b[lastYear] ?? 0) - (a[lastYear] ?? 0);
        }).slice(0, 8);
        const yearKeys = year_over_year.years.map((y: any) => String(y.year));
        const YEAR_COLORS = ["#a5b4fc", "#c4b5fd", "#7c6af7"];

        return (
          <div style={SECTION}>
            <h2 style={{ margin: "0 0 16px", fontSize: 16 }}>📊 Year-over-Year</h2>
            <div style={{ display: "flex", gap: 12, marginBottom: 20 }}>
              {year_over_year.years.map((y: any) => (
                <div key={y.year} style={{ flex: 1, background: "#f9fafb", borderRadius: 8, padding: "12px 16px", textAlign: "center" }}>
                  <div style={{ fontSize: 12, color: "#9ca3af", marginBottom: 4 }}>
                    {y.is_partial ? `${y.year} YTD (${year_over_year.same_period_label})` : `${y.year} full year`}
                  </div>
                  <div style={{ fontSize: 22, fontWeight: 700 }}>
                    ${y.total.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                  </div>
                  {y.is_partial && year_over_year.same_period_pct_change !== null && (
                    <div style={{ fontSize: 12, marginTop: 2, color: year_over_year.same_period_pct_change > 0 ? "#92400e" : "#065f46" }}>
                      {year_over_year.same_period_pct_change > 0 ? "+" : ""}{year_over_year.same_period_pct_change}% vs same period last year
                    </div>
                  )}
                </div>
              ))}
              {year_over_year.on_pace !== null && (
                <div style={{
                  flex: 1,
                  background: (year_over_year.on_pace_pct_change ?? 0) > 0 ? "#fef3c7" : "#d1fae5",
                  borderRadius: 8, padding: "12px 16px", textAlign: "center",
                }}>
                  <div style={{ fontSize: 12, color: "#9ca3af", marginBottom: 4 }}>On pace for {year_over_year.years.at(-1)?.year}</div>
                  <div style={{ fontSize: 22, fontWeight: 700 }}>
                    ${year_over_year.on_pace.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                  </div>
                  {year_over_year.on_pace_pct_change !== null && (
                    <div style={{
                      fontSize: 12, marginTop: 2,
                      color: year_over_year.on_pace_pct_change > 0 ? "#92400e" : "#065f46",
                    }}>
                      {year_over_year.on_pace_pct_change > 0 ? "+" : ""}{year_over_year.on_pace_pct_change}% vs {year_over_year.years.at(-2)?.year} full year
                    </div>
                  )}
                </div>
              )}
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
                <XAxis dataKey="category" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`} />
                <Tooltip
                  formatter={(value: number, name: string) => [`$${(value as number).toFixed(0)}`, name]}
                  contentStyle={{ background: "#1a1a2e", border: "none", borderRadius: 8, color: "#fff", fontSize: 12 }}
                />
                {yearKeys.map((yr, i) => (
                  <Bar key={yr} dataKey={yr} fill={YEAR_COLORS[i % YEAR_COLORS.length]} radius={[3, 3, 0, 0]} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        );
      })()}
      {/* Monthly Averages */}
      <div style={{ marginTop: 32 }}>
        <div style={{ fontSize: 18, fontWeight: 700, color: "#fff", marginBottom: 16 }}>
          Average Monthly Spending
        </div>

        {/* Controls */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
          {([3, 6, 12] as const).map((m) => (
            <button
              key={m}
              onClick={() => { setAvgMonths(m); setAvgDateFrom(""); setAvgDateTo(""); }}
              style={{
                padding: "6px 16px", borderRadius: 8, border: "none", cursor: "pointer", fontSize: 13,
                background: avgMonths === m && !avgDateFrom ? "#7c6af7" : "#312e81",
                color: avgMonths === m && !avgDateFrom ? "#fff" : "#a5b4fc",
              }}
            >
              {m}M
            </button>
          ))}
          <span style={{ color: "#6b7280", fontSize: 13 }}>or</span>
          <input
            type="date"
            value={avgDateFrom}
            onChange={(e) => setAvgDateFrom(e.target.value)}
            style={{ background: "#312e81", border: "none", borderRadius: 8, padding: "6px 10px", color: "#e0e7ff", fontSize: 13 }}
          />
          <span style={{ color: "#6b7280", fontSize: 13 }}>–</span>
          <input
            type="date"
            value={avgDateTo}
            onChange={(e) => setAvgDateTo(e.target.value)}
            style={{ background: "#312e81", border: "none", borderRadius: 8, padding: "6px 10px", color: "#e0e7ff", fontSize: 13 }}
          />
        </div>

        {avgLoading && <div style={{ color: "#9ca3af", padding: 20 }}>Loading...</div>}

        {avgData && !avgLoading && (
          <>
            {/* Total average card */}
            <div style={{ background: "#1e1b4b", borderRadius: 12, padding: "20px 24px", marginBottom: 16 }}>
              <div style={{ fontSize: 12, color: "#9ca3af", marginBottom: 4 }}>Monthly average</div>
              <div style={{ fontSize: 32, fontWeight: 700, color: "#fff" }}>
                ${avgData.total_avg.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
              </div>
              <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 4 }}>
                avg over {avgData.months_count} complete month{avgData.months_count !== 1 ? "s" : ""}
                {avgData.months_count === 0 ? " — no complete months in range" : ` (${avgData.date_from} – ${avgData.date_to})`}
              </div>
            </div>

            {/* Per-category table */}
            {avgData.categories.length > 0 && (
              <div style={{ background: "#1e1b4b", borderRadius: 12, padding: "20px 24px" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
                  <thead>
                    <tr style={{ color: "#9ca3af", fontSize: 12, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                      <th style={{ textAlign: "left", paddingBottom: 10, fontWeight: 600 }}>Category</th>
                      <th style={{ textAlign: "right", paddingBottom: 10, fontWeight: 600 }}>Avg / month</th>
                      <th style={{ textAlign: "right", paddingBottom: 10, fontWeight: 600 }}>% of total</th>
                      <th style={{ textAlign: "right", paddingBottom: 10, fontWeight: 600 }}>Months with spend</th>
                    </tr>
                  </thead>
                  <tbody>
                    {avgData.categories.map((cat: any, i: number) => (
                      <tr
                        key={cat.category}
                        onClick={() => {
                          const params = new URLSearchParams({ category: cat.category });
                          if (avgDateFrom) params.set("dateFrom", avgDateFrom);
                          if (avgDateTo) params.set("dateTo", avgDateTo);
                          window.location.href = `/transactions?${params.toString()}`;
                        }}
                        style={{
                          borderTop: "1px solid #312e81", cursor: "pointer",
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = "#312e81")}
                        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                      >
                        <td style={{ padding: "10px 0", color: "#e0e7ff", textTransform: "capitalize" }}>{cat.category}</td>
                        <td style={{ padding: "10px 0", textAlign: "right", color: "#c4b5fd", fontWeight: 600 }}>
                          ${cat.avg.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                        </td>
                        <td style={{ padding: "10px 0", textAlign: "right", color: "#9ca3af" }}>{cat.pct}%</td>
                        <td style={{ padding: "10px 0", textAlign: "right", color: "#9ca3af" }}>
                          {cat.months_with_spend} / {avgData.months_count}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
