import { useEffect, useRef, useState } from "react";
import { getOverview, triggerSync, getConfiguredBanks, importFromFolder, uploadCSV, triggerEnrichment, getEnrichStatus, triggerRecategorize, getAccounts, createAccount, previewCSV, getDataQuality } from "../api/client";
import type { BankAccount, DataQuality, ImportSummary } from "../api/client";
import { previewRequestKey, samePreviewRequest } from "../api/reliabilityHelpers";
import type { PreviewRequestKey } from "../api/reliabilityHelpers";
import { SpendingLineChart } from "../components/SpendingLineChart";
import { CategoryStackedBar } from "../components/CategoryStackedBar";

const CARD_STYLE = {
  background: "#fff", borderRadius: 10, padding: "16px 20px",
  boxShadow: "0 1px 4px rgba(0,0,0,0.07)", flex: 1,
};

function errorDetail(error: unknown, fallback: string): string {
  if (typeof error !== "object" || error === null) return fallback;
  const value = error as { response?: { data?: { detail?: unknown } }; message?: unknown };
  if (typeof value.response?.data?.detail === "string") return value.response.data.detail;
  return typeof value.message === "string" ? value.message : fallback;
}

export function Overview() {
  const [data, setData] = useState<any>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [banks, setBanks] = useState<Record<string, boolean>>({});
  const [syncing, setSyncing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [uploadBank, setUploadBank] = useState("chase");
  const [accounts, setAccounts] = useState<BankAccount[]>([]);
  const [accountsError, setAccountsError] = useState<string | null>(null);
  const [selectedAccount, setSelectedAccount] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewResult, setPreviewResult] = useState<{ key: PreviewRequestKey; result: ImportSummary } | null>(null);
  const [importSummary, setImportSummary] = useState<ImportSummary | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [accountName, setAccountName] = useState("");
  const [accountLast4, setAccountLast4] = useState("");
  const [quality, setQuality] = useState<DataQuality | null>(null);
  const [qualityError, setQualityError] = useState<string | null>(null);
  const [enriching, setEnriching] = useState(false);
  const [enrichMsg, setEnrichMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const previewGeneration = useRef(0);
  const confirmingImport = useRef(false);

  async function refreshAccounts() {
    try { setAccounts(await getAccounts()); setAccountsError(null); }
    catch { setAccountsError("Accounts could not be loaded."); }
  }

  async function refreshQuality() {
    try { setQuality(await getDataQuality()); setQualityError(null); }
    catch { setQualityError("Data coverage details could not be loaded."); }
  }

  useEffect(() => {
    getOverview().then(setData).catch((e) => setLoadError(e.message));
    getConfiguredBanks().then(setBanks).catch(() => {});
    getAccounts().then((loaded) => { setAccounts(loaded); setAccountsError(null); }).catch(() => setAccountsError("Accounts could not be loaded."));
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

  const handleFolderImport = async () => {
    setImporting(true);
    setImportMsg(null);
    try {
      const result = await importFromFolder();
      setImportMsg(`Imported ${result.total_new_transactions} new transactions from ${result.files_processed} file(s).`);
      const fresh = await getOverview();
      setData(fresh);
      refreshQuality();
    } catch (e: any) {
      setImportMsg(`Import failed: ${e?.response?.data?.detail ?? e.message}`);
    } finally {
      setImporting(false);
    }
  };

  const handleRecategorize = async () => {
    setEnriching(true);
    setEnrichMsg("Starting re-categorization…");
    try {
      await triggerRecategorize();
      const poll = async (): Promise<void> => {
        const s = await getEnrichStatus();
        if (s.status === "error") {
          setEnrichMsg(`Re-categorize failed: ${s.error}`);
          setEnriching(false);
        } else if (s.status === "done") {
          setEnrichMsg(`Done — ${s.done} transactions re-categorized.`);
          setEnriching(false);
        } else if (s.status === "running") {
          const progress = s.total > 0 ? ` (${s.done}/${s.total})` : "";
          setEnrichMsg(`Re-categorizing${progress}…`);
          setTimeout(poll, 2000);
        } else {
          setEnrichMsg("Re-categorize queued, starting…");
          setTimeout(poll, 1000);
        }
      };
      setTimeout(poll, 1000);
    } catch (e: any) {
      setEnrichMsg(`Re-categorize failed: ${e?.response?.data?.detail ?? e.message}`);
      setEnriching(false);
    }
  };

  const handleEnrich = async () => {
    setEnriching(true);
    setEnrichMsg("Starting enrichment…");
    try {
      await triggerEnrichment();
      const poll = async (): Promise<void> => {
        const s = await getEnrichStatus();
        if (s.status === "error") {
          setEnrichMsg(`Enrichment failed: ${s.error}`);
          setEnriching(false);
        } else if (s.status === "done") {
          setEnrichMsg(`Done — ${s.done} transactions enriched.`);
          setEnriching(false);
        } else if (s.status === "running") {
          const progress = s.total > 0 ? ` (${s.done}/${s.total})` : "";
          setEnrichMsg(`Enriching transactions${progress}…`);
          setTimeout(poll, 2000);
        } else {
          // pending — job queued, not started yet
          setEnrichMsg("Enrichment queued, starting…");
          setTimeout(poll, 1000);
        }
      };
      setTimeout(poll, 1000);
    } catch (e: any) {
      setEnrichMsg(`Enrichment failed: ${e?.response?.data?.detail ?? e.message}`);
      setEnriching(false);
    }
  };

  const currentPreviewKey = selectedFile ? previewRequestKey(selectedFile, uploadBank, selectedAccount) : null;
  const preview = previewResult && samePreviewRequest(previewResult.key, currentPreviewKey) ? previewResult.result : null;

  const invalidatePreview = () => {
    previewGeneration.current += 1;
    setPreviewResult(null);
    setPreviewing(false);
    setImportSummary(null);
    setImportMsg(null);
  };

  const runPreview = async (file: File, bank = uploadBank, accountId = selectedAccount) => {
    const generation = ++previewGeneration.current;
    const key = previewRequestKey(file, bank, accountId);
    setPreviewResult(null);
    setImportSummary(null);
    setPreviewing(true);
    setImportMsg(null);
    try {
      const result = await previewCSV(bank, file, accountId || undefined);
      if (generation === previewGeneration.current) setPreviewResult({ key, result });
    } catch (error) {
      if (generation === previewGeneration.current) setImportMsg(`Preview failed: ${errorDetail(error, "Could not preview this file.")}`);
    } finally {
      if (generation === previewGeneration.current) setPreviewing(false);
    }
  };

  const handleFileSelection = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    setImportSummary(null);
    await runPreview(file);
    if (fileRef.current) fileRef.current.value = "";
  };

  const handleConfirmImport = async () => {
    const key = currentPreviewKey;
    if (confirmingImport.current || !key || !previewResult || !samePreviewRequest(previewResult.key, key)) return;
    confirmingImport.current = true;
    setImporting(true);
    setImportMsg(null);
    try {
      const file = key.file as File;
      const result = await uploadCSV(key.bank, file, key.accountId || undefined);
      setImportSummary(result);
      setImportMsg(`Import complete: ${result.new_transactions} new transaction${result.new_transactions === 1 ? "" : "s"}.`);
      setSelectedFile(null);
      const fresh = await getOverview();
      setData(fresh);
      refreshQuality();
    } catch (error) {
      setImportMsg(`Import failed: ${errorDetail(error, "Could not import this file.")}`);
    } finally { confirmingImport.current = false; setImporting(false); }
  };

  const handleCreateAccount = async () => {
    if (!accountName.trim()) return;
    try {
      const created = await createAccount({ bank: uploadBank, name: accountName.trim(), last4: accountLast4.trim() || undefined });
      setAccounts((current) => [...current, created]);
      setSelectedAccount(created.id);
      setAccountName(""); setAccountLast4("");
    } catch (error) {
      setImportMsg(`Could not add account: ${errorDetail(error, "Please try again.")}`);
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

      <section aria-label="Data coverage and freshness" style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: "14px 18px", marginBottom: 24, boxShadow: "0 1px 4px rgba(0,0,0,0.04)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <strong style={{ fontSize: 14 }}>Data coverage and freshness</strong>
          {qualityError && <button onClick={refreshQuality} style={{ border: "1px solid #ddd", borderRadius: 6, background: "#fff", padding: "5px 10px", cursor: "pointer" }}>Retry</button>}
        </div>
        {qualityError ? <p role="alert" style={{ margin: "8px 0 0", color: "#b91c1c", fontSize: 13 }}>{qualityError}</p> : quality ? <>
          <p style={{ margin: "7px 0 10px", color: "#4b5563", fontSize: 13 }}>{quality.coverage_note || "These dates show observed transactions; they do not confirm complete statement coverage."}</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 18px", color: "#4b5563", fontSize: 12 }}>
            {quality.sources.map((source) => (
              <span key={source.source}><strong>{source.source}</strong>: {source.transaction_count} transactions, observed {source.first_date ?? "—"} to {source.last_date ?? "—"}</span>
            ))}
            <span>{quality.total_transactions ?? 0} transactions total</span>
            <span>{quality.missing_city ?? 0} with unknown city</span>
            <span>{quality.missing_merchant ?? 0} with unknown merchant</span>
            <span>{quality.unassigned_account ?? 0} without an assigned account</span>
          </div>
          <p style={{ margin: "8px 0 0", color: "#6b7280", fontSize: 12 }}>A recent transaction date does not prove that an account or statement period is complete. Unknown cities are excluded from confident location matching.</p>
        </> : <p role="status" style={{ margin: "8px 0 0", color: "#6b7280", fontSize: 13 }}>Loading coverage details…</p>}
      </section>

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
          <select value={uploadBank} disabled={importing} onChange={(e) => { invalidatePreview(); setUploadBank(e.target.value); setSelectedAccount(""); }} style={{
            border: "1px solid #ddd", borderRadius: 6, padding: "6px 10px", fontSize: 13,
          }}>
            <option value="chase">Chase</option>
            <option value="amex">Amex</option>
            <option value="discover">Discover</option>
          </select>
          <select aria-label="Account for import" value={selectedAccount} disabled={importing} onChange={(e) => { invalidatePreview(); setSelectedAccount(e.target.value); }} style={{ border: "1px solid #ddd", borderRadius: 6, padding: "6px 10px", fontSize: 13 }}>
            <option value="">No account selected</option>
            {accounts.filter((account) => account.bank.toLowerCase() === uploadBank.toLowerCase()).map((account) => (
              <option key={account.id} value={account.id}>{account.name}{account.last4 ? ` ••${account.last4}` : ""}</option>
            ))}
          </select>
          {accountsError && <span role="alert" style={{ color: "#b91c1c", fontSize: 12 }}>{accountsError} <button onClick={refreshAccounts} style={{ border: "1px solid #ddd", borderRadius: 5, background: "#fff", padding: "3px 7px", cursor: "pointer" }}>Retry</button></span>}
          <label style={{
            background: "#fff", border: "1px solid #c9c0f8", borderRadius: 8,
            padding: "6px 14px", cursor: "pointer", fontSize: 13, color: "#7c6af7",
          }}>
            Choose file
            <input ref={fileRef} type="file" accept=".csv,.CSV" style={{ display: "none" }} onChange={handleFileSelection} disabled={importing} />
          </label>
        </div>
        <details style={{ marginTop: 10, fontSize: 13 }}>
          <summary style={{ cursor: "pointer", color: "#5544b8" }}>Add a bank account</summary>
          <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
            <input aria-label="Account name" value={accountName} onChange={(e) => setAccountName(e.target.value)} placeholder="Account name" style={{ padding: "6px 9px", border: "1px solid #ddd", borderRadius: 6 }} />
            <input aria-label="Last four digits" value={accountLast4} onChange={(e) => setAccountLast4(e.target.value.slice(0, 4))} placeholder="Last four (optional)" inputMode="numeric" style={{ width: 140, padding: "6px 9px", border: "1px solid #ddd", borderRadius: 6 }} />
            <button onClick={handleCreateAccount} disabled={!accountName.trim()} style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #c9c0f8", background: "#fff", cursor: "pointer" }}>Add account</button>
          </div>
        </details>
        {previewing && <div role="status" style={{ marginTop: 10, color: "#555", fontSize: 13 }}>Checking {selectedFile?.name}…</div>}
        {selectedFile && !preview && !previewing && <button onClick={() => runPreview(selectedFile)} disabled={importing} style={{ marginTop: 8, border: "1px solid #c9c0f8", borderRadius: 6, background: "#fff", padding: "6px 12px", cursor: "pointer" }}>Preview {selectedFile.name} again</button>}
        {(preview || (!selectedFile ? importSummary : null)) && <div style={{ marginTop: 10, background: "#fff", border: "1px solid #ddd6fe", borderRadius: 8, padding: 12, fontSize: 13 }}>
          <strong>{preview && selectedFile ? `Preview: ${selectedFile.name}` : "Import results"}</strong>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 8 }}>
            {(() => { const summary = preview ?? importSummary; return summary ? <><span>Rows: {summary.input_rows}</span><span>Accepted: {summary.parsed_rows}</span><span>Rejected: {summary.rejected_rows}</span><span>Duplicates: {summary.duplicate_rows}</span><span>New: {summary.new_transactions}</span></> : null; })()}
          </div>
          {(preview ?? importSummary)?.warnings?.map((warning, index) => <p key={index} style={{ margin: "8px 0 0", color: "#92400e" }}>{warning}</p>)}
          {(preview ?? importSummary)?.errors?.length ? <details style={{ marginTop: 8 }}><summary style={{ cursor: "pointer", color: "#b91c1c" }}>Rejected rows and reasons ({(preview ?? importSummary)?.errors.length})</summary><ul style={{ margin: "6px 0", paddingLeft: 20, maxHeight: 180, overflow: "auto" }}>{(preview ?? importSummary)?.errors.map((row, index) => <li key={`${row.row_number}-${index}`}>Row {row.row_number}: {row.reason}</li>)}</ul></details> : null}
          {preview && selectedFile && <button onClick={handleConfirmImport} disabled={importing || !samePreviewRequest(previewResult?.key ?? null, currentPreviewKey) || preview.new_transactions === 0} style={{ marginTop: 10, background: "#7c6af7", color: "#fff", border: 0, borderRadius: 7, padding: "7px 14px", cursor: "pointer" }}>{importing ? "Importing…" : `Import ${preview.new_transactions} new transaction${preview.new_transactions === 1 ? "" : "s"}`}</button>}
        </div>}
        <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <button onClick={handleEnrich} disabled={enriching} style={{
            background: "#10b981", color: "#fff", border: "none",
            borderRadius: 8, padding: "7px 16px", cursor: "pointer", fontSize: 13,
          }}>
            {enriching ? "Enriching…" : "Enrich new transactions"}
          </button>
          <button onClick={handleRecategorize} disabled={enriching} style={{
            background: "#7c6af7", color: "#fff", border: "none",
            borderRadius: 8, padding: "7px 16px", cursor: "pointer", fontSize: 13,
          }}>
            {enriching ? "Working…" : "Re-categorize all with AI"}
          </button>
          <span style={{ color: "#6b7280", fontSize: 12 }}>Re-categorize updates all categories using AI</span>
        </div>
        {importMsg && (
          <div role="status" style={{ marginTop: 10, fontSize: 13, color: importMsg.includes("complete") ? "#047857" : "#b91c1c" }}>
            {importMsg}
          </div>
        )}
        {enrichMsg && (
          <div style={{ marginTop: 6, fontSize: 13, color: enrichMsg.startsWith("Done") ? "#0a0" : enrichMsg.startsWith("Enrichment failed") ? "#e05" : "#555" }}>
            {enrichMsg}
          </div>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 16, marginBottom: 32 }}>
        <div style={CARD_STYLE}>
          <div style={{ color: "#888", fontSize: 12, marginBottom: 4 }}>Gross Purchases This Month</div>
          <div style={{ fontSize: 28, fontWeight: 700 }}>${currentTotal.toFixed(2)}</div>
        </div>
        <div style={CARD_STYLE}>
          <div style={{ color: "#888", fontSize: 12, marginBottom: 4 }}>Refunds This Month</div>
          <div style={{ fontSize: 28, fontWeight: 700 }}>{currentMetrics ? `$${currentMetrics.refunds.toFixed(2)}` : "Not available"}</div>
        </div>
        <div style={CARD_STYLE}>
          <div style={{ color: "#888", fontSize: 12, marginBottom: 4 }}>Net Spending This Month</div>
          <div style={{ fontSize: 28, fontWeight: 700 }}>{currentMetrics ? `$${currentMetrics.net_spending.toFixed(2)}` : "Not available"}</div>
        </div>
        <div style={CARD_STYLE}>
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
