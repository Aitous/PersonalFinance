import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getOverview, triggerSync, getConfiguredBanks, getDataQuality } from "../api/client";
import type { DataQuality } from "../api/client";
import { SpendingLineChart } from "../components/SpendingLineChart";
import { CategoryStackedBar } from "../components/CategoryStackedBar";

const CARD_STYLE = {
  background: "#fff", borderRadius: 10, padding: "16px 20px",
  boxShadow: "0 1px 4px rgba(0,0,0,0.07)", flex: 1,
};

export function Overview() {
  const [data, setData] = useState<any>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [banks, setBanks] = useState<Record<string, boolean>>({});
  const [syncing, setSyncing] = useState(false);
  const [quality, setQuality] = useState<DataQuality | null>(null);
  const [qualityError, setQualityError] = useState<string | null>(null);

  async function refreshQuality() {
    try { setQuality(await getDataQuality()); setQualityError(null); }
    catch { setQualityError("Data coverage details could not be loaded."); }
  }

  useEffect(() => {
    getOverview().then(setData).catch((e) => setLoadError(e.message));
    getConfiguredBanks().then(setBanks).catch(() => {});
    getDataQuality().then((loaded) => { setQuality(loaded); setQualityError(null); }).catch(() => setQualityError("Data coverage details could not be loaded."));
  }, []);

  const handleSync = async () => {
    setSyncing(true);
    try {
      const since = new Date();
      since.setMonth(since.getMonth() - 3);
      const sinceStr = since.toISOString().split("T")[0];
      const activeBanks = Object.entries(banks).filter(([, v]) => v).map(([k]) => k);
      await Promise.all(activeBanks.map((bank) => triggerSync(bank, sinceStr)));
      const fresh = await getOverview();
      setData(fresh);
      refreshQuality();
    } finally {
      setSyncing(false);
    }
  };

  if (loadError) return <div role="alert" style={{ color: "#b91c1c" }}>Failed to load overview: {loadError} <button onClick={() => { setLoadError(null); getOverview().then(setData).catch((e) => setLoadError(e.message)); }} style={{ marginLeft: 8, border: "1px solid #ddd", borderRadius: 6, background: "#fff", padding: "5px 10px", cursor: "pointer" }}>Retry</button></div>;
  if (!data) return <p>Loading…</p>;

  const noData = Object.keys(data.monthly).length === 0;

  const months = Object.keys(data.monthly).sort().slice(-12);
  const lineData = months.map((m) => ({ month: m, total: data.monthly[m]?.total ?? 0 }));

  const allCats = new Set<string>();
  const metricKeys = new Set(["total", "gross_purchases", "refunds", "net_spending"]);
  months.forEach((m) => Object.keys(data.monthly[m] ?? {}).filter((k) => !metricKeys.has(k)).forEach((c) => allCats.add(c)));
  const categories = Array.from(allCats);
  const barData = months.slice(-6).map((m) => ({
    month: m, ...Object.fromEntries(categories.map((c) => [c, data.monthly[m]?.[c] ?? 0])),
  }));

  const currentMonth = months[months.length - 1] ?? "";
  const prevMonth = months[months.length - 2] ?? "";
  const currentTotal = data.monthly[currentMonth]?.total ?? 0;
  const currentMetrics = data.monthly_totals?.[currentMonth];
  const prevTotal = data.monthly[prevMonth]?.total ?? 0;

  // Normalize current month to a full-month pace for fair comparison
  const today = new Date();
  const isCurrentMonth = currentMonth === `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
  const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
  const daysPassed = today.getDate();
  const currentPace = isCurrentMonth && daysPassed < daysInMonth
    ? (currentTotal / daysPassed) * daysInMonth
    : currentTotal;
  const pctChange = prevTotal !== 0 ? (((currentPace - prevTotal) / prevTotal) * 100).toFixed(1) : null;
  const isPaceEstimate = isCurrentMonth && daysPassed < daysInMonth;

  return (
    <div className="overview-page">
      <div className="overview-hero">
        <div>
          <div className="overview-eyebrow"><span className="overview-eyebrow-dot" /> YOUR PERSONAL FINANCE OVERVIEW</div>
          <h1 style={{ margin: "8px 0 4px", fontSize: 34 }}>A clearer picture<br /><em>of your money.</em></h1>
          <p className="overview-subtitle">The details behind your spending, all in one place.</p>
        </div>
        <button onClick={handleSync} disabled={syncing} style={{
          background: "#287c61", color: "#fff", border: "none",
          borderRadius: 8, padding: "8px 20px", cursor: "pointer", fontSize: 14,
        }}>
          {syncing ? "Syncing…" : "Sync Now"}
        </button>
      </div>

      <div className="overview-section-heading">
        <div><span className="section-kicker">YOUR SPENDING SNAPSHOT</span><h2>At a glance</h2></div>
        <span className="section-period">{currentMonth ? new Date(`${currentMonth}-01T12:00:00`).toLocaleDateString(undefined, { month: "long", year: "numeric" }) : "No activity yet"}</span>
      </div>

      <section aria-label="Data freshness" style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: "14px 18px", marginBottom: 24, boxShadow: "0 1px 4px rgba(0,0,0,0.04)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <strong style={{ fontSize: 14 }}>Data freshness</strong>
          {qualityError && <button onClick={refreshQuality} style={{ border: "1px solid #ddd", borderRadius: 6, background: "#fff", padding: "5px 10px", cursor: "pointer" }}>Retry</button>}
        </div>
        {qualityError ? <p role="alert" style={{ margin: "8px 0 0", color: "#b91c1c", fontSize: 13 }}>{qualityError}</p> : quality ? <>
          <p style={{ margin: "7px 0 8px", color: "#4b5563", fontSize: 13 }}>{quality.total_transactions} imported transactions across {quality.sources.length} sources. {quality.missing_category} uncategorized; {quality.enrichment_fallback} enrichment fallbacks.</p>
          <p style={{ margin: "0 0 8px", color: "#6b7280", fontSize: 12 }}>Observed activity does not confirm complete statement-period coverage.</p>
          <Link to="/settings#data-coverage" style={{ color: "#276c54", fontSize: 12, fontWeight: 700 }}>Review imports & data coverage →</Link>
        </> : <p role="status" style={{ margin: "8px 0 0", color: "#6b7280", fontSize: 13 }}>Loading coverage details…</p>}
      </section>

      <div className="overview-metrics" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 16, marginBottom: 32 }}>
        <div className="overview-metric-card metric-purchases" style={CARD_STYLE}>
          <div style={{ color: "#888", fontSize: 12, marginBottom: 4 }}>Gross purchases</div>
          <div style={{ fontSize: 28, fontWeight: 700 }}>${currentTotal.toFixed(2)}</div>
        </div>
        <div className="overview-metric-card metric-refunds" style={CARD_STYLE}>
          <div style={{ color: "#888", fontSize: 12, marginBottom: 4 }}>Refunds</div>
          <div style={{ fontSize: 28, fontWeight: 700 }}>{currentMetrics ? `$${currentMetrics.refunds.toFixed(2)}` : "Not available"}</div>
        </div>
        <div className="overview-metric-card metric-net" style={CARD_STYLE}>
          <div style={{ color: "#888", fontSize: 12, marginBottom: 4 }}>Net spending</div>
          <div style={{ fontSize: 28, fontWeight: 700 }}>{currentMetrics ? `$${currentMetrics.net_spending.toFixed(2)}` : "Not available"}</div>
        </div>
        <div className="overview-metric-card metric-change" style={CARD_STYLE}>
          <div style={{ color: "#888", fontSize: 12, marginBottom: 4 }}>
            vs Last Month{isPaceEstimate ? " (projected pace)" : ""}
          </div>
          <div style={{ fontSize: 28, fontWeight: 700, color: pctChange === null ? "#888" : Number(pctChange) > 0 ? "#e05" : "#0a0" }}>
            {pctChange === null ? "—" : `${Number(pctChange) > 0 ? "+" : ""}${pctChange}%`}
          </div>
          {isPaceEstimate && (
            <div style={{ color: "#9ca3af", fontSize: 11, marginTop: 2 }}>
              Based on {daysPassed}d of {daysInMonth}
            </div>
          )}
        </div>
      </div>

      {noData ? (
        <div style={{ textAlign: "center", padding: "48px 0", color: "#888" }}>
          No transactions yet. <Link to="/settings">Import a statement to get started.</Link>
        </div>
      ) : (
        <>
          <div className="overview-chart-panel" style={{ background: "#fff", borderRadius: 10, padding: 24, marginBottom: 24, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
            <h2 style={{ margin: "0 0 16px", fontSize: 16 }}>Total Monthly Spending (12 months)</h2>
            <SpendingLineChart data={lineData} />
          </div>

          <div className="overview-chart-panel" style={{ background: "#fff", borderRadius: 10, padding: 24, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
            <h2 style={{ margin: "0 0 16px", fontSize: 16 }}>Spending by Category (6 months)</h2>
            <CategoryStackedBar data={barData} categories={categories} />
          </div>
        </>
      )}
    </div>
  );
}
