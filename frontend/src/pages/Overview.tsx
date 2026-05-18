import { useEffect, useState } from "react";
import { getOverview, triggerSync, getConfiguredBanks } from "../api/client";
import { SpendingLineChart } from "../components/SpendingLineChart";
import { CategoryStackedBar } from "../components/CategoryStackedBar";

const CARD_STYLE = {
  background: "#fff", borderRadius: 10, padding: "16px 20px",
  boxShadow: "0 1px 4px rgba(0,0,0,0.07)", flex: 1,
};

export function Overview() {
  const [data, setData] = useState<any>(null);
  const [banks, setBanks] = useState<Record<string, boolean>>({});
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    getOverview().then(setData);
    getConfiguredBanks().then(setBanks);
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
    } finally {
      setSyncing(false);
    }
  };

  if (!data) return <p>Loading...</p>;

  const months = Object.keys(data.monthly).sort().slice(-12);
  const lineData = months.map((m) => ({ month: m, total: data.monthly[m]?.total ?? 0 }));

  const allCats = new Set<string>();
  months.forEach((m) => Object.keys(data.monthly[m] ?? {}).filter((k) => k !== "total").forEach((c) => allCats.add(c)));
  const categories = Array.from(allCats);
  const barData = months.slice(-6).map((m) => ({
    month: m, ...Object.fromEntries(categories.map((c) => [c, data.monthly[m]?.[c] ?? 0])),
  }));

  const currentMonth = months[months.length - 1];
  const prevMonth = months[months.length - 2];
  const currentTotal = data.monthly[currentMonth]?.total ?? 0;
  const prevTotal = data.monthly[prevMonth]?.total ?? 1;
  const pctChange = (((currentTotal - prevTotal) / prevTotal) * 100).toFixed(1);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 24 }}>Overview</h1>
        <button onClick={handleSync} disabled={syncing} style={{
          background: "#7c6af7", color: "#fff", border: "none",
          borderRadius: 8, padding: "8px 20px", cursor: "pointer", fontSize: 14,
        }}>
          {syncing ? "Syncing…" : "Sync Now"}
        </button>
      </div>

      <div style={{ display: "flex", gap: 16, marginBottom: 32 }}>
        <div style={CARD_STYLE}>
          <div style={{ color: "#888", fontSize: 12, marginBottom: 4 }}>Total Spent This Month</div>
          <div style={{ fontSize: 28, fontWeight: 700 }}>${currentTotal.toFixed(2)}</div>
        </div>
        <div style={CARD_STYLE}>
          <div style={{ color: "#888", fontSize: 12, marginBottom: 4 }}>vs Last Month</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: Number(pctChange) > 0 ? "#e05" : "#0a0" }}>
            {Number(pctChange) > 0 ? "+" : ""}{pctChange}%
          </div>
        </div>
      </div>

      <div style={{ background: "#fff", borderRadius: 10, padding: 24, marginBottom: 24, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
        <h2 style={{ margin: "0 0 16px", fontSize: 16 }}>Total Monthly Spending (12 months)</h2>
        <SpendingLineChart data={lineData} />
      </div>

      <div style={{ background: "#fff", borderRadius: 10, padding: 24, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
        <h2 style={{ margin: "0 0 16px", fontSize: 16 }}>Spending by Category (6 months)</h2>
        <CategoryStackedBar data={barData} categories={categories} />
      </div>
    </div>
  );
}
