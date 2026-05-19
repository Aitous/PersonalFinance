import { useEffect, useRef, useState } from "react";
import { getOverview, triggerSync, getConfiguredBanks, importFromFolder, uploadCSV, triggerEnrichment, getEnrichStatus } from "../api/client";
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
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [uploadBank, setUploadBank] = useState("chase");
  const [enriching, setEnriching] = useState(false);
  const [enrichMsg, setEnrichMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getOverview().then(setData).catch((e) => setLoadError(e.message));
    getConfiguredBanks().then(setBanks).catch(() => {});
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

  const handleFolderImport = async () => {
    setImporting(true);
    setImportMsg(null);
    try {
      const result = await importFromFolder();
      setImportMsg(`Imported ${result.total_new_transactions} new transactions from ${result.files_processed} file(s).`);
      const fresh = await getOverview();
      setData(fresh);
    } catch (e: any) {
      setImportMsg(`Import failed: ${e?.response?.data?.detail ?? e.message}`);
    } finally {
      setImporting(false);
    }
  };

  const handleEnrich = async () => {
    setEnriching(true);
    setEnrichMsg("Starting enrichment…");
    try {
      await triggerEnrichment();
      // Poll until the job finishes
      const poll = async (): Promise<void> => {
        const status = await getEnrichStatus();
        if (status.error) {
          setEnrichMsg(`Enrichment failed: ${status.error}`);
          setEnriching(false);
          return;
        }
        if (status.running || status.total === 0) {
          const progress = status.total > 0
            ? ` (${status.done}/${status.total})`
            : "";
          setEnrichMsg(`Enriching transactions${progress}…`);
          setTimeout(poll, 2000);
        } else {
          setEnrichMsg(`Done — ${status.done} transactions enriched.`);
          setEnriching(false);
        }
      };
      setTimeout(poll, 1000);
    } catch (e: any) {
      setEnrichMsg(`Enrichment failed: ${e?.response?.data?.detail ?? e.message}`);
      setEnriching(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setImportMsg(null);
    try {
      const result = await uploadCSV(uploadBank, file);
      setImportMsg(`Imported ${result.tx_count} new transactions from ${file.name}.`);
      const fresh = await getOverview();
      setData(fresh);
    } catch (e: any) {
      setImportMsg(`Upload failed: ${e?.response?.data?.detail ?? e.message}`);
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  if (loadError) return <p style={{ color: "red" }}>Failed to load overview: {loadError}</p>;
  if (!data) return <p>Loading…</p>;

  const noData = Object.keys(data.monthly).length === 0;

  const months = Object.keys(data.monthly).sort().slice(-12);
  const lineData = months.map((m) => ({ month: m, total: data.monthly[m]?.total ?? 0 }));

  const allCats = new Set<string>();
  months.forEach((m) => Object.keys(data.monthly[m] ?? {}).filter((k) => k !== "total").forEach((c) => allCats.add(c)));
  const categories = Array.from(allCats);
  const barData = months.slice(-6).map((m) => ({
    month: m, ...Object.fromEntries(categories.map((c) => [c, data.monthly[m]?.[c] ?? 0])),
  }));

  const currentMonth = months[months.length - 1] ?? "";
  const prevMonth = months[months.length - 2] ?? "";
  const currentTotal = data.monthly[currentMonth]?.total ?? 0;
  const prevTotal = data.monthly[prevMonth]?.total ?? 0;
  const pctChange = prevTotal !== 0 ? (((currentTotal - prevTotal) / prevTotal) * 100).toFixed(1) : null;

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

      <div style={{ background: "#f0edff", border: "1px solid #c9c0f8", borderRadius: 10, padding: "16px 20px", marginBottom: 24 }}>
        <div style={{ fontWeight: 600, marginBottom: 10, fontSize: 14 }}>Import Transactions from CSV</div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <button onClick={handleFolderImport} disabled={importing} style={{
            background: "#7c6af7", color: "#fff", border: "none",
            borderRadius: 8, padding: "7px 16px", cursor: "pointer", fontSize: 13,
          }}>
            {importing ? "Importing…" : "Import from transactions/ folder"}
          </button>
          <span style={{ color: "#888", fontSize: 13 }}>or upload a file:</span>
          <select value={uploadBank} onChange={(e) => setUploadBank(e.target.value)} style={{
            border: "1px solid #ddd", borderRadius: 6, padding: "6px 10px", fontSize: 13,
          }}>
            <option value="chase">Chase</option>
            <option value="amex">Amex</option>
            <option value="discover">Discover</option>
          </select>
          <label style={{
            background: "#fff", border: "1px solid #c9c0f8", borderRadius: 8,
            padding: "6px 14px", cursor: "pointer", fontSize: 13, color: "#7c6af7",
          }}>
            Choose file
            <input ref={fileRef} type="file" accept=".csv,.CSV" style={{ display: "none" }} onChange={handleFileUpload} disabled={importing} />
          </label>
        </div>
        <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 10 }}>
          <button onClick={handleEnrich} disabled={enriching} style={{
            background: "#10b981", color: "#fff", border: "none",
            borderRadius: 8, padding: "7px 16px", cursor: "pointer", fontSize: 13,
          }}>
            {enriching ? "Enriching…" : "Enrich all transactions with AI"}
          </button>
          <span style={{ color: "#6b7280", fontSize: 12 }}>Extracts merchant names, cities, and types for all banks</span>
        </div>
        {importMsg && (
          <div style={{ marginTop: 10, fontSize: 13, color: importMsg.startsWith("Import") && !importMsg.includes("failed") ? "#0a0" : "#e05" }}>
            {importMsg}
          </div>
        )}
        {enrichMsg && (
          <div style={{ marginTop: 6, fontSize: 13, color: enrichMsg.startsWith("Done") ? "#0a0" : enrichMsg.startsWith("Enrichment failed") ? "#e05" : "#555" }}>
            {enrichMsg}
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: 16, marginBottom: 32 }}>
        <div style={CARD_STYLE}>
          <div style={{ color: "#888", fontSize: 12, marginBottom: 4 }}>Total Spent This Month</div>
          <div style={{ fontSize: 28, fontWeight: 700 }}>${currentTotal.toFixed(2)}</div>
        </div>
        <div style={CARD_STYLE}>
          <div style={{ color: "#888", fontSize: 12, marginBottom: 4 }}>vs Last Month</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: pctChange === null ? "#888" : Number(pctChange) > 0 ? "#e05" : "#0a0" }}>
            {pctChange === null ? "—" : `${Number(pctChange) > 0 ? "+" : ""}${pctChange}%`}
          </div>
        </div>
      </div>

      {noData ? (
        <div style={{ textAlign: "center", padding: "48px 0", color: "#888" }}>
          No transactions yet. Import your CSVs above to get started.
        </div>
      ) : (
        <>
          <div style={{ background: "#fff", borderRadius: 10, padding: 24, marginBottom: 24, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
            <h2 style={{ margin: "0 0 16px", fontSize: 16 }}>Total Monthly Spending (12 months)</h2>
            <SpendingLineChart data={lineData} />
          </div>

          <div style={{ background: "#fff", borderRadius: 10, padding: 24, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
            <h2 style={{ margin: "0 0 16px", fontSize: 16 }}>Spending by Category (6 months)</h2>
            <CategoryStackedBar data={barData} categories={categories} />
          </div>
        </>
      )}
    </div>
  );
}
