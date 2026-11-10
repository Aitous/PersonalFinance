import { useEffect, useRef, useState } from "react";
import { confirmImportInbox, createAccount, getAccounts, getDataQuality, getEnrichStatus, getImportBatches, getImportInbox, previewCSV, previewImportInbox, triggerEnrichment, uploadCSV } from "../api/client";
import type { BankAccount, DataQuality, ImportBatchSummary, ImportInboxFile, ImportSummary, InboxPreview } from "../api/client";
import { previewRequestKey, samePreviewRequest } from "../api/reliabilityHelpers";
import type { PreviewRequestKey } from "../api/reliabilityHelpers";
import { useRecategorization } from "./recategorizationContext";
import { hostedMode } from "../auth";

function errorDetail(error: unknown, fallback: string): string {
  if (typeof error !== "object" || error === null) return fallback;
  const value = error as { response?: { data?: { detail?: unknown } }; message?: unknown };
  if (typeof value.response?.data?.detail === "string") return value.response.data.detail;
  return typeof value.message === "string" ? value.message : fallback;
}

const SECTION: React.CSSProperties = { background: "#fff", border: "1px solid #e2e8df", borderRadius: 12, padding: 20, marginBottom: 20, boxShadow: "0 2px 8px rgba(35,68,45,.04)" };

export function ImportWorkspace() {
  const recategorization = useRecategorization();
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
  const [importBatches, setImportBatches] = useState<ImportBatchSummary[]>([]);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [enriching, setEnriching] = useState(false);
  const [enrichMsg, setEnrichMsg] = useState<string | null>(null);
  const [inboxFiles, setInboxFiles] = useState<ImportInboxFile[]>([]);
  const [inboxFolder, setInboxFolder] = useState("transactions/inbox");
  const [inboxLoading, setInboxLoading] = useState(true);
  const [inboxError, setInboxError] = useState<string | null>(null);
  const [selectedInboxFile, setSelectedInboxFile] = useState<string | null>(null);
  const [inboxBank, setInboxBank] = useState("");
  const [inboxAccountId, setInboxAccountId] = useState("");
  const [inboxPreview, setInboxPreview] = useState<InboxPreview | null>(null);
  const [inboxPreviewing, setInboxPreviewing] = useState(false);
  const [inboxConfirming, setInboxConfirming] = useState(false);
  const [inboxMsg, setInboxMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const previewGeneration = useRef(0);
  const inboxPreviewGeneration = useRef(0);
  const confirmingImport = useRef(false);

  async function refreshAccounts() {
    try { setAccounts(await getAccounts()); setAccountsError(null); }
    catch { setAccountsError("Accounts could not be loaded."); }
  }
  async function refreshQuality() {
    try { setQuality(await getDataQuality()); setQualityError(null); }
    catch { setQualityError("Data coverage details could not be loaded."); }
  }
  async function refreshImportBatches() {
    try { setImportBatches(await getImportBatches()); setBatchError(null); }
    catch { setBatchError("Recent import history could not be loaded."); }
  }

  async function refreshInbox() {
    try {
      const listing = await getImportInbox();
      setInboxFiles(listing.files);
      setInboxFolder(listing.folder);
      setInboxError(null);
    } catch {
      setInboxError("The local import inbox could not be scanned.");
    } finally {
      setInboxLoading(false);
    }
  }

  useEffect(() => {
    void refreshAccounts();
    void refreshQuality();
    void refreshImportBatches();
    if (!hostedMode) void refreshInbox();
    const timer = hostedMode ? undefined : window.setInterval(() => void refreshInbox(), 8000);
    return () => { if (timer) window.clearInterval(timer); };
  }, []);

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

  const handleFileSelection = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    setImportSummary(null);
    await runPreview(file);
    if (fileRef.current) fileRef.current.value = "";
  };

  const handlePreviewInbox = async () => {
    if (!selectedInboxFile) return;
    const generation = ++inboxPreviewGeneration.current;
    setInboxPreview(null);
    setInboxPreviewing(true);
    setInboxMsg(null);
    try {
      const result = await previewImportInbox(selectedInboxFile, inboxBank, inboxAccountId || undefined);
      if (generation === inboxPreviewGeneration.current) setInboxPreview(result);
    } catch (error) {
      if (generation === inboxPreviewGeneration.current) setInboxMsg(`Preview failed: ${errorDetail(error, "Could not preview this file.")}`);
    } finally {
      if (generation === inboxPreviewGeneration.current) setInboxPreviewing(false);
    }
  };

  const handleConfirmInboxImport = async () => {
    if (!selectedInboxFile || !inboxPreview || inboxPreview.filename !== selectedInboxFile) return;
    setInboxConfirming(true);
    setInboxMsg(null);
    try {
      const result = await confirmImportInbox({
        filename: selectedInboxFile,
        bank: inboxBank,
        account_id: inboxAccountId || undefined,
        checksum: inboxPreview.checksum,
      });
      setInboxMsg(`Imported ${result.new_transactions} new transaction${result.new_transactions === 1 ? "" : "s"}. An archive copy is in transactions/processed; this inbox copy is marked imported so it can be moved out when convenient.`);
      setSelectedInboxFile(null);
      setInboxPreview(null);
      void refreshInbox();
      void refreshQuality();
      void refreshImportBatches();
    } catch (error) {
      setInboxMsg(`Import failed: ${errorDetail(error, "Could not import this file.")}`);
      if (errorDetail(error, "").includes("changed after preview")) {
        setInboxPreview(null);
      }
      void refreshInbox();
    } finally {
      setInboxConfirming(false);
    }
  };

  const handleSelectInboxFile = (file: ImportInboxFile) => {
    inboxPreviewGeneration.current += 1;
    setInboxPreviewing(false);
    setSelectedInboxFile(file.filename);
    setInboxBank(file.bank_guess || "");
    setInboxAccountId("");
    setInboxPreview(null);
    setInboxMsg(null);
  };

  const invalidateInboxPreview = () => {
    inboxPreviewGeneration.current += 1;
    setInboxPreview(null);
    setInboxPreviewing(false);
  };

  const handleConfirmImport = async () => {
    const key = currentPreviewKey;
    if (confirmingImport.current || !key || !previewResult || !samePreviewRequest(previewResult.key, key)) return;
    confirmingImport.current = true;
    setImporting(true);
    setImportMsg(null);
    try {
      const result = await uploadCSV(key.bank, key.file as File, key.accountId || undefined);
      setImportSummary(result);
      setImportMsg(`Import complete: ${result.new_transactions} new transaction${result.new_transactions === 1 ? "" : "s"}.`);
      setSelectedFile(null);
      void refreshQuality();
      void refreshImportBatches();
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
      setAccountName("");
      setAccountLast4("");
    } catch (error) { setImportMsg(`Could not add account: ${errorDetail(error, "Please try again.")}`); }
  };

  const handleEnrich = async () => {
    setEnriching(true);
    setEnrichMsg("Starting enrichment…");
    try {
      await triggerEnrichment();
      const poll = async (): Promise<void> => {
        const status = await getEnrichStatus("enrich");
        if (status.status === "error") { setEnrichMsg(`Enrichment failed: ${status.error}`); setEnriching(false); }
        else if (status.status === "done") { setEnrichMsg(`Done — ${status.done} transactions enriched.`); setEnriching(false); void refreshQuality(); }
        else if (status.status === "running") {
          setEnrichMsg(`Enriching transactions${status.total > 0 ? ` (${status.done}/${status.total})` : ""}…`);
          setTimeout(poll, 2000);
        } else { setEnrichMsg("Enrichment queued, starting…"); setTimeout(poll, 1000); }
      };
      setTimeout(poll, 1000);
    } catch (error: any) {
      setEnrichMsg(`Enrichment failed: ${error?.response?.data?.detail ?? error.message}`);
      setEnriching(false);
    }
  };

  return <div>
    {!hostedMode && <section className="import-inbox-section" aria-labelledby="import-inbox-heading">
      <div className="import-inbox-header">
        <div>
          <h2 id="import-inbox-heading">Downloaded files inbox</h2>
          <p>Move bank CSVs into <code>{inboxFolder}/</code>. The app checks this local folder while Settings is open; nothing is imported until you review and confirm it.</p>
        </div>
        <button onClick={() => void refreshInbox()} disabled={inboxLoading}>{inboxLoading ? "Checking…" : "Refresh inbox"}</button>
      </div>
      {inboxError ? <p role="alert" className="import-error">{inboxError} <button onClick={() => void refreshInbox()}>Retry</button></p>
        : inboxLoading ? <p role="status">Checking {inboxFolder}/…</p>
        : inboxFiles.length === 0 ? <div className="import-inbox-empty"><strong>No CSV files waiting</strong><span>Downloaded statements stay on your Mac. Copy a CSV into {inboxFolder}/ to review it here.</span></div>
        : <div className="import-inbox-files">{inboxFiles.map((file) => <article key={file.filename} className={selectedInboxFile === file.filename ? "is-selected" : ""}>
          <div className="import-inbox-file-main"><strong>{file.filename}</strong><span>{file.bank_guess ? file.bank_guess.toUpperCase() : "Choose bank"} · {(file.size_bytes / 1024).toFixed(0)} KB · {new Date(file.modified_at).toLocaleString()}</span></div>
          {file.already_imported ? <span className="import-inbox-warning">Already imported · move this copy out of the inbox</span>
            : file.too_large ? <span className="import-inbox-warning">Over 25 MiB</span>
            : <button onClick={() => handleSelectInboxFile(file)} disabled={inboxConfirming}>{selectedInboxFile === file.filename ? "Selected" : "Review"}</button>}
        </article>)}</div>}

      {selectedInboxFile && <div className="import-inbox-review">
        <div className="import-inbox-review-heading"><strong>Review {selectedInboxFile}</strong><button className="import-inbox-dismiss" disabled={inboxConfirming} onClick={() => { invalidateInboxPreview(); setSelectedInboxFile(null); setInboxMsg(null); }}>Close</button></div>
        <div className="import-inbox-controls">
          <label>Bank<select value={inboxBank} disabled={inboxConfirming} onChange={(event) => { invalidateInboxPreview(); setInboxAccountId(""); setInboxBank(event.target.value); }}>
            <option value="" disabled>Choose bank</option><option value="chase">Chase</option><option value="discover">Discover</option><option value="amex">Amex</option>
          </select></label>
          <label>Account<select value={inboxAccountId} disabled={inboxConfirming} onChange={(event) => { invalidateInboxPreview(); setInboxAccountId(event.target.value); }}>
            <option value="">No account selected</option>
            {accounts.filter((account) => account.bank.toLowerCase() === inboxBank).map((account) => <option key={account.id} value={account.id}>{account.name}{account.last4 ? ` ••${account.last4}` : ""}</option>)}
          </select></label>
          <button onClick={() => void handlePreviewInbox()} disabled={!inboxBank || inboxPreviewing || inboxConfirming}>{inboxPreviewing ? "Previewing…" : inboxPreview ? "Refresh preview" : "Preview file"}</button>
        </div>
        {inboxPreviewing && <p role="status">Reading CSV and checking for duplicates…</p>}
        {inboxPreview && inboxPreview.filename === selectedInboxFile && <div className="import-preview-summary">
          <strong>Preview summary</strong>
          <div className="import-preview-stats"><span>Rows: {inboxPreview.input_rows}</span><span>Accepted: {inboxPreview.parsed_rows}</span><span>Rejected: {inboxPreview.rejected_rows}</span><span>Already imported: {inboxPreview.duplicate_rows}</span><span>New: {inboxPreview.new_transactions}</span></div>
          {inboxPreview.warnings.map((warning, index) => <p key={index} className="import-warning">{warning}</p>)}
          {inboxPreview.sample_transactions.length > 0 && <div className="import-inbox-samples"><strong>Sample transactions</strong><div>{inboxPreview.sample_transactions.map((tx, index) => <span key={`${tx.date}-${index}`}><time>{tx.date}</time><b>{tx.description}</b><em>{tx.amount < 0 ? "−" : ""}${Math.abs(tx.amount).toFixed(2)}</em></span>)}</div></div>}
          {inboxPreview.errors.length > 0 && <details><summary>Rejected rows and reasons ({inboxPreview.errors.length})</summary><ul>{inboxPreview.errors.map((row, index) => <li key={`${row.row_number}-${index}`}>Row {row.row_number}: {row.reason}</li>)}</ul></details>}
          <button className="import-inbox-confirm" onClick={() => void handleConfirmInboxImport()} disabled={inboxConfirming || inboxPreview.new_transactions === 0}>{inboxConfirming ? "Importing…" : `Confirm import of ${inboxPreview.new_transactions} new transaction${inboxPreview.new_transactions === 1 ? "" : "s"}`}</button>
          {inboxPreview.new_transactions === 0 && <small>This file has no new transactions to add.</small>}
        </div>}
      </div>}
      {inboxMsg && <p role="status" className={inboxMsg.includes("failed") ? "import-error" : "import-success"}>{inboxMsg}</p>}
    </section>}

    <section style={SECTION}>
      <h2 style={{ margin: "0 0 6px", fontSize: 18 }}>Import transactions</h2>
      <p style={{ margin: "0 0 16px", color: "#687973", fontSize: 13 }}>Import a statement, preview its rows, and confirm what will be added.</p>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ color: "#888", fontSize: 13 }}>or preview one file directly:</span>
        <select aria-label="Bank for CSV import" value={uploadBank} disabled={importing} onChange={(event) => { invalidatePreview(); setUploadBank(event.target.value); setSelectedAccount(""); }}>
          <option value="chase">Chase</option><option value="amex">Amex</option><option value="discover">Discover</option>
        </select>
        <select aria-label="Account for import" value={selectedAccount} disabled={importing} onChange={(event) => { invalidatePreview(); setSelectedAccount(event.target.value); }}>
          <option value="">No account selected</option>
          {accounts.filter((account) => account.bank.toLowerCase() === uploadBank.toLowerCase()).map((account) => <option key={account.id} value={account.id}>{account.name}{account.last4 ? ` ••${account.last4}` : ""}</option>)}
        </select>
        {accountsError && <span role="alert" style={{ color: "#b91c1c", fontSize: 12 }}>{accountsError} <button onClick={() => void refreshAccounts()}>Retry</button></span>}
        <label className="import-file-button">Choose CSV<input ref={fileRef} type="file" accept=".csv,.CSV" onChange={handleFileSelection} disabled={importing} /></label>
      </div>
      <details style={{ marginTop: 12, fontSize: 13 }}>
        <summary style={{ cursor: "pointer", color: "#276c54" }}>Add a bank account</summary>
        <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
          <input aria-label="Account name" value={accountName} onChange={(event) => setAccountName(event.target.value)} placeholder="Account name" />
          <input aria-label="Last four digits" value={accountLast4} onChange={(event) => setAccountLast4(event.target.value.slice(0, 4))} placeholder="Last four (optional)" inputMode="numeric" />
          <button onClick={handleCreateAccount} disabled={!accountName.trim()}>Add account</button>
        </div>
      </details>
      {previewing && <p role="status">Checking {selectedFile?.name}…</p>}
      {selectedFile && !preview && !previewing && <button onClick={() => void runPreview(selectedFile)} disabled={importing}>Preview {selectedFile.name} again</button>}
      {(preview || (!selectedFile ? importSummary : null)) && <div className="import-preview-summary">
        <strong>{preview && selectedFile ? `Preview: ${selectedFile.name}` : "Import results"}</strong>
        <div className="import-preview-stats">{(() => { const summary = preview ?? importSummary; return summary ? <><span>Rows: {summary.input_rows}</span><span>Accepted: {summary.parsed_rows}</span><span>Rejected: {summary.rejected_rows}</span><span>Duplicates: {summary.duplicate_rows}</span><span>New: {summary.new_transactions}</span></> : null; })()}</div>
        {(preview ?? importSummary)?.warnings?.map((warning, index) => <p key={index} className="import-warning">{warning}</p>)}
        {(preview ?? importSummary)?.errors?.length ? <details><summary>Rejected rows and reasons ({(preview ?? importSummary)?.errors.length})</summary><ul>{(preview ?? importSummary)?.errors.map((row, index) => <li key={`${row.row_number}-${index}`}>Row {row.row_number}: {row.reason}</li>)}</ul></details> : null}
        {preview && selectedFile && <button onClick={handleConfirmImport} disabled={importing || !samePreviewRequest(previewResult?.key ?? null, currentPreviewKey) || preview.new_transactions === 0}>{importing ? "Importing…" : `Import ${preview.new_transactions} new transaction${preview.new_transactions === 1 ? "" : "s"}`}</button>}
      </div>}
      {importMsg && <p role="status" className={importMsg.includes("failed") || importMsg.includes("Could not") ? "import-error" : "import-success"}>{importMsg}</p>}
    </section>

    <section style={SECTION}>
      <h2 style={{ margin: "0 0 6px", fontSize: 18 }}>Transaction processing</h2>
      <p style={{ margin: "0 0 14px", color: "#687973", fontSize: 13 }}>Enrichment fills in merchant details. Re-categorization updates categories using AI and may take a while.</p>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <button className="settings-button settings-button-primary" onClick={handleEnrich} disabled={enriching}>{enriching ? "Enriching…" : "Enrich new transactions"}</button>
        <button className="settings-button settings-button-secondary" onClick={() => void recategorization.start()} disabled={enriching || recategorization.active}>{recategorization.active ? "Re-categorizing…" : "Re-categorize all with AI"}</button>
        {enrichMsg && <span role="status">{enrichMsg}</span>}
      </div>
    </section>

    <section style={SECTION}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>Data coverage & import history</h2>
        <button onClick={() => { void refreshQuality(); void refreshImportBatches(); }}>Refresh</button>
      </div>
      {qualityError ? <p role="alert" className="import-error">{qualityError}</p> : quality ? <>
        <p style={{ color: "#687973", fontSize: 13 }}>{quality.coverage_note || "Observed transaction dates do not confirm complete statement coverage."}</p>
        <div className="coverage-metrics"><strong>{quality.total_transactions} transactions</strong><span>{quality.sources.length} imported sources</span><span>{quality.missing_merchant} unknown merchants</span><span>{quality.missing_city} unknown cities</span><span>{quality.missing_category} uncategorized</span><span>{quality.enrichment_fallback} enrichment fallbacks</span><span>{quality.unassigned_account} without an account</span></div>
        <div className="coverage-sources">{quality.sources.map((source) => <span key={source.source}><strong>{source.source}</strong> · {source.transaction_count} rows · {source.first_date} to {source.last_date}</span>)}</div>
      </> : <p role="status">Loading data coverage…</p>}
      <h3 style={{ margin: "20px 0 8px", fontSize: 14 }}>Recent CSV imports</h3>
      {batchError ? <p role="alert" className="import-error">{batchError}</p> : importBatches.length ? <div className="import-history-list">{importBatches.map((batch) => <article key={batch.id}>
        <strong>{batch.bank} · {batch.filename}</strong><span>{new Date(batch.created_at).toLocaleString()}</span><span>Observed {batch.from_date ?? "—"} to {batch.to_date ?? "—"}</span><span>{batch.new_transactions} new · {batch.duplicate_rows} duplicates · {batch.rejected_rows} rejected</span>
      </article>)}</div> : <p style={{ color: "#687973", fontSize: 13 }}>No CSV imports recorded yet.</p>}
    </section>
  </div>;
}
