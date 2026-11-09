import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { getTransactions, updateTransactionCategory, updateTransactionCategories, updateTransactionDetails, deleteTransaction, searchTransactions, getTransactionProvenance } from "../api/client";
import type { TransactionProvenance } from "../api/client";
import { readTransactionFilters, writeTransactionFilters } from "../api/transactionFilters";
import { fetchAllSearchResults } from "../api/searchPagination";
import { selectionTotalCents, toggleVisibleSelection } from "../api/transactionSelection";

const CATEGORIES = [
  "dining", "groceries", "transport", "shopping", "entertainment",
  "subscriptions", "health", "travel", "utilities", "other",
];

const CATEGORY_COLORS: Record<string, string> = {
  dining: "#287c61", groceries: "#9bc68b", transport: "#d6a967",
  shopping: "#60a5fa", entertainment: "#34d399", subscriptions: "#f59e0b",
  health: "#f87171", travel: "#38bdf8", utilities: "#94a3b8", other: "#d1d5db",
};
const SORT_FIELDS = ["date", "description", "source", "category", "amount"] as const;
const SEARCH_PAGE_SIZE = 50;

interface Transaction {
  id: string;
  date: string;
  description: string;
  source: string;
  category: string;
  amount: number;
  merchant_name?: string | null;
  merchant_type?: string | null;
  city?: string | null;
  is_online?: boolean | null;
  is_subscription?: boolean;
  match_type?: string;
  [key: string]: unknown;
}

export function Transactions() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const initialFilters = readTransactionFilters(searchParams);
  const lastWrittenUrl = useRef("");
  const skipWrite = useRef(false);
  const [txs, setTxs] = useState<Transaction[]>([]);
  const [selected, setSelected] = useState<Record<string, Transaction>>({});
  const [bulkCategory, setBulkCategory] = useState("");
  const [bulkSaving, setBulkSaving] = useState(false);
  const [bulkMessage, setBulkMessage] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [detailsEditorId, setDetailsEditorId] = useState<string | null>(null);
  const [detailsDraft, setDetailsDraft] = useState({ merchant_name: "", city: "", merchant_type: "", is_online: "unknown" });
  const [detailsSaving, setDetailsSaving] = useState(false);
  const [detailsError, setDetailsError] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [provenance, setProvenance] = useState<{ id: string; data?: TransactionProvenance; error?: string; loading?: boolean } | null>(null);
  const [filterCategory, setFilterCategory] = useState(initialFilters.category ?? "");
  const [filterSource, setFilterSource] = useState(initialFilters.source ?? "");
  const [txType, setTxType] = useState<"spending" | "refunds" | "all">(initialFilters.tx_type === "refunds" || initialFilters.tx_type === "all" ? initialFilters.tx_type : "spending");
  const [dateFrom, setDateFrom] = useState(initialFilters.date_from ?? "");
  const [dateTo, setDateTo] = useState(initialFilters.date_to ?? "");
  const [sortField, setSortField] = useState<(typeof SORT_FIELDS)[number]>(SORT_FIELDS.includes(initialFilters.sort as (typeof SORT_FIELDS)[number]) ? initialFilters.sort as (typeof SORT_FIELDS)[number] : "date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">(initialFilters.sort_dir === "asc" ? "asc" : "desc");
  const [searchQuery, setSearchQuery] = useState(initialFilters.q ?? "");
  const [searchMode, setSearchMode] = useState<"hybrid" | "keyword" | "semantic">(initialFilters.search_mode === "keyword" || initialFilters.search_mode === "semantic" ? initialFilters.search_mode : "hybrid");
  const [searchMeta, setSearchMeta] = useState<{ embedded_count?: number; total?: number; total_results: number } | null>(null);
  const [searchPage, setSearchPage] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const urlFilters = useMemo(() => readTransactionFilters(searchParams), [searchParams]);
  const filterMonth = urlFilters.month ?? "";
  const filterMerchant = urlFilters.merchant ?? "";
  const filterIds = urlFilters.ids ?? "";
  const [columns, setColumns] = useState<Record<string, string>>({
    description: initialFilters.description ?? "", merchant_contains: initialFilters.merchant_contains ?? "",
    city: initialFilters.city ?? "", merchant_type: initialFilters.merchant_type ?? "",
    min_amount: initialFilters.min_amount ?? "", max_amount: initialFilters.max_amount ?? "",
    is_online: initialFilters.is_online ?? "", is_subscription: initialFilters.is_subscription ?? "",
  });
  const [loadedKey, setLoadedKey] = useState("");
  const [loadError, setLoadError] = useState("");
  const paramsKey = JSON.stringify({
    category: filterCategory || undefined, source: filterSource || undefined,
    month: filterMonth || undefined, merchant: filterMerchant || undefined,
    tx_type: txType, date_from: dateFrom || undefined, date_to: dateTo || undefined,
    ids: filterIds || undefined,
    description: columns.description || undefined, merchant_contains: columns.merchant_contains || undefined,
    city: columns.city || undefined, merchant_type: columns.merchant_type || undefined,
    min_amount: columns.min_amount || undefined, max_amount: columns.max_amount || undefined,
    is_online: columns.is_online || undefined, is_subscription: columns.is_subscription || undefined,
    ...Object.fromEntries(Object.entries(columns).map(([key, value]) => [key, value || undefined])),
  });
  const searchDefinition = JSON.stringify([paramsKey, searchQuery.trim(), searchMode]);
  const previousSearchDefinition = useRef(searchDefinition);
  const requestKey = JSON.stringify([searchDefinition, searchPage]);
  const pending = loadedKey !== requestKey;
  const invalidRange = (!!columns.min_amount && !!columns.max_amount && Number(columns.min_amount) > Number(columns.max_amount)) || (!!dateFrom && !!dateTo && dateFrom > dateTo);
  const clearFilters = () => {
    setFilterCategory(""); setFilterSource(""); setDateFrom(""); setDateTo("");
    setSearchQuery(""); setColumns({}); setTxType("spending"); setSortField("date"); setSortDir("desc"); setSearchMode("hybrid"); navigate("/transactions");
  };

  useEffect(() => {
    if (previousSearchDefinition.current !== searchDefinition) {
      previousSearchDefinition.current = searchDefinition;
      setSearchPage(0);
    }
  }, [searchDefinition]);

  // URL is the source of truth for shareable filters, including history navigation.
  useEffect(() => {
    const serialized = writeTransactionFilters(urlFilters).toString();
    if (serialized === lastWrittenUrl.current) { lastWrittenUrl.current = ""; return; }
    skipWrite.current = true;
    setSearchQuery(urlFilters.q ?? "");
    setFilterCategory(urlFilters.category ?? "");
    setFilterSource(urlFilters.source ?? "");
    setDateFrom(urlFilters.date_from ?? "");
    setDateTo(urlFilters.date_to ?? "");
    setTxType(urlFilters.tx_type === "refunds" || urlFilters.tx_type === "all" ? urlFilters.tx_type : "spending");
    setSearchMode(urlFilters.search_mode === "keyword" || urlFilters.search_mode === "semantic" ? urlFilters.search_mode : "hybrid");
    setSortField(SORT_FIELDS.includes(urlFilters.sort as (typeof SORT_FIELDS)[number]) ? urlFilters.sort as (typeof SORT_FIELDS)[number] : "date");
    setSortDir(urlFilters.sort_dir === "asc" ? "asc" : "desc");
    setColumns({
      description: urlFilters.description ?? "", merchant_contains: urlFilters.merchant_contains ?? "",
      city: urlFilters.city ?? "", merchant_type: urlFilters.merchant_type ?? "",
      min_amount: urlFilters.min_amount ?? "", max_amount: urlFilters.max_amount ?? "",
      is_online: urlFilters.is_online ?? "", is_subscription: urlFilters.is_subscription ?? "",
    });
  }, [searchParams, urlFilters]);

  useEffect(() => {
    if (skipWrite.current) { skipWrite.current = false; return; }
    const next = writeTransactionFilters({
      ...urlFilters,
      q: searchQuery.trim(), category: filterCategory, source: filterSource,
      date_from: dateFrom, date_to: dateTo,
      ...columns, tx_type: txType, search_mode: searchMode, sort: sortField, sort_dir: sortDir,
    });
    if (next.toString() === writeTransactionFilters(urlFilters).toString()) return;
    lastWrittenUrl.current = next.toString();
    setSearchParams(next, { replace: true });
  }, [searchQuery, filterCategory, filterSource, dateFrom, dateTo, columns, txType, searchMode, sortField, sortDir, searchParams, setSearchParams, urlFilters]);

  // Ignore stale responses when filters change while a request is in flight.
  useEffect(() => {
    if (invalidRange) return;
    let active = true;
    const timer = setTimeout(async () => {
      setIsSearching(true); setLoadError("");
      try {
        const filters = JSON.parse(paramsKey);
        if (searchQuery.trim()) {
          const data = await searchTransactions(searchQuery.trim(), searchMode, filters, {
            offset: searchPage * SEARCH_PAGE_SIZE, limit: SEARCH_PAGE_SIZE,
          });
          if (active) {
            setTxs(data.results);
            setSearchMeta({ embedded_count: data.embedded_count, total: data.total_transactions, total_results: data.total_results });
            setLoadedKey(requestKey);
          }
        } else {
          const data = await getTransactions(filters);
          if (active) { setTxs(data); setSearchMeta(null); setLoadedKey(requestKey); }
        }
      } catch {
        if (active) { setTxs([]); setLoadError("Could not load transactions. Please try again."); }
      } finally {
        if (active) setIsSearching(false);
      }
    }, 350);
    return () => { active = false; clearTimeout(timer); };
  }, [paramsKey, searchQuery, searchMode, searchPage, invalidRange, requestKey]);

  const handleCategoryChange = async (id: string, category: string) => {
    await updateTransactionCategory(id, category);
    setTxs((prev) => prev.filter(tx => tx.id !== id || !filterCategory || category === filterCategory).map((tx) => tx.id === id ? { ...tx, category } : tx));
    setEditingId(null);
  };

  const startDetailsEdit = (tx: Transaction) => {
    setDetailsEditorId(tx.id);
    setDetailsError("");
    setDetailsDraft({
      merchant_name: tx.merchant_name ?? "", city: tx.city ?? "", merchant_type: tx.merchant_type ?? "",
      is_online: tx.is_online === true ? "true" : tx.is_online === false ? "false" : "unknown",
    });
  };

  const loadProvenance = async (id: string) => {
    setProvenance({ id, loading: true });
    try {
      const data = await getTransactionProvenance(id);
      setProvenance((current) => current?.id === id ? { id, data } : current);
    } catch {
      setProvenance((current) => current?.id === id ? { id, error: "Could not load transaction history. Please try again." } : current);
    }
  };

  const saveDetails = async (tx: Transaction) => {
    setDetailsSaving(true);
    setDetailsError("");
    const patch = {
      merchant_name: detailsDraft.merchant_name.trim() || null,
      city: detailsDraft.city.trim() || null,
      merchant_type: detailsDraft.merchant_type.trim() || null,
      is_online: detailsDraft.is_online === "unknown" ? null : detailsDraft.is_online === "true",
    };
    try {
      const response = await updateTransactionDetails(tx.id, patch);
      setTxs((current) => current.map((item) => item.id === tx.id ? { ...item, ...patch, ...(response ?? {}) } : item));
      setDetailsEditorId(null);
    } catch (error) {
      const message = (error as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
        ?? (error as { message?: string })?.message
        ?? "Could not save transaction details.";
      setDetailsError(message);
    } finally { setDetailsSaving(false); }
  };

  const handleDelete = async (tx: Transaction) => {
    const confirmed = window.confirm(`Delete this transaction?\n\n${tx.description} · ${tx.date}\n\nYou can re-import it from the original statement.`);
    if (!confirmed) return;
    setDeletingId(tx.id);
    setDeleteError("");
    try {
      await deleteTransaction(tx.id);
      setTxs((current) => current.filter((item) => item.id !== tx.id));
      setSelected((current) => { const next = { ...current }; delete next[tx.id]; return next; });
      setExpandedId((current) => current === tx.id ? null : current);
      setEditingId((current) => current === tx.id ? null : current);
      setDetailsEditorId((current) => current === tx.id ? null : current);
    } catch (error) {
      const message = (error as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
        ?? (error as { message?: string })?.message
        ?? "Could not delete transaction. Please try again.";
      setDeleteError(message);
    } finally {
      setDeletingId(null);
    }
  };

  const toggleSort = (field: typeof sortField) => {
    if (sortField === field) setSortDir((d) => d === "asc" ? "desc" : "asc");
    else { setSortField(field); setSortDir("desc"); }
  };

  const sortTransactions = (items: Transaction[]) => [...items].sort((a, b) => {
    const mul = sortDir === "asc" ? 1 : -1;
    if (sortField === "amount") return mul * (a.amount - b.amount);
    return mul * String(a[sortField] ?? "").localeCompare(String(b[sortField] ?? ""));
  });
  const sortedTxs = sortTransactions(txs);
  const selectedCount = Object.keys(selected).length;
  const selectedTotal = selectionTotalCents(selected) / 100;
  const selectedVisibleCount = sortedTxs.filter((tx) => !!selected[tx.id]).length;
  const allVisibleSelected = sortedTxs.length > 0 && selectedVisibleCount === sortedTxs.length;

  const applyBulkCategory = async () => {
    const ids = Object.keys(selected);
    if (!ids.length || !bulkCategory || bulkSaving) return;
    setBulkSaving(true); setBulkMessage("");
    try {
      const result = await updateTransactionCategories(ids, bulkCategory);
      const chosen = new Set(ids);
      setTxs((current) => current.filter((tx) => !chosen.has(tx.id) || !filterCategory || filterCategory === bulkCategory)
        .map((tx) => chosen.has(tx.id) ? { ...tx, category: bulkCategory } : tx));
      setSelected({});
      setBulkMessage(`Updated ${result.updated} transaction${result.updated === 1 ? "" : "s"}. Manual categories are preserved during AI re-categorization.`);
      setBulkCategory("");
    } catch (error) {
      setBulkMessage((error as { response?: { data?: { detail?: string } } }).response?.data?.detail || "Could not update categories. No changes were made; please try again.");
    } finally { setBulkSaving(false); }
  };

  const handleExport = async () => {
    setExporting(true);
    setExportError("");
    try {
      const rows = searchQuery.trim()
        ? await fetchAllSearchResults((offset, limit) => searchTransactions(
          searchQuery.trim(), searchMode, JSON.parse(paramsKey), { offset, limit },
        ))
        : sortedTxs;
      const keys = ["date", "description", "merchant_name", "category", "amount", "source", "city", "merchant_type", "is_online", "is_subscription"];
      const escape = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
      const csv = [keys, ...sortTransactions(rows).map(tx => keys.map(key => tx[key]))].map(row => row.map(escape).join(",")).join("\r\n");
      const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
      const link = document.createElement("a"); link.href = url; link.download = "transactions.csv"; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      setExportError("Could not export all matching transactions. Please try again.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 20 }}>Transactions</h1>

      {filterIds && (
        <div style={{ background: "#fef3c7", border: "1px solid #f59e0b", borderRadius: 8, padding: "10px 16px", marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 13 }}>
          <span>⚠ Showing {txs.length} flagged transaction{txs.length !== 1 ? "s" : ""} from an insight alert</span>
          <span onClick={() => navigate("/transactions")} style={{ cursor: "pointer", color: "#92400e", fontWeight: 600 }}>Clear ×</span>
        </div>
      )}

      {/* Search bar */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <div style={{ position: "relative", flex: 1 }}>
            <span style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "#9ca3af", fontSize: 16 }}>🔍</span>
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder='Search — try "coffee in San Mateo", "streaming services", "bay area dining"…'
              style={{ width: "100%", padding: "10px 12px 10px 36px", borderRadius: 8, border: "1.5px solid #e5e7eb", fontSize: 14, boxSizing: "border-box", outline: "none" }}
              onFocus={(e) => e.target.style.borderColor = "#287c61"}
              onBlur={(e) => e.target.style.borderColor = "#e5e7eb"}
            />
            {searchQuery && (
              <span onClick={() => setSearchQuery("")} style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", cursor: "pointer", color: "#9ca3af", fontSize: 18 }}>×</span>
            )}
          </div>
          <div style={{ display: "flex", gap: 4, background: "#f3f4f6", borderRadius: 8, padding: 3 }}>
            {(["hybrid", "keyword", "semantic"] as const).map((m) => (
              <button key={m} onClick={() => setSearchMode(m)} style={{
                padding: "5px 10px", borderRadius: 6, fontSize: 12, border: "none", cursor: "pointer",
                background: searchMode === m ? "#287c61" : "transparent",
                color: searchMode === m ? "#fff" : "#6b7280",
                fontWeight: searchMode === m ? 600 : 400,
              }}>{m}</button>
            ))}
          </div>
        </div>
        {searchQuery && searchMeta && (
          <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 6 }}>
            {isSearching ? "Searching…" : searchMeta.total_results === 0 ? "No matching transactions" : `Showing ${searchPage * SEARCH_PAGE_SIZE + 1}–${Math.min((searchPage + 1) * SEARCH_PAGE_SIZE, searchMeta.total_results)} of ${searchMeta.total_results} matching transactions`}
            {searchMeta.embedded_count !== undefined && searchMeta.embedded_count < (searchMeta.total ?? 0) && (
              <span style={{ marginLeft: 8, color: "#f59e0b" }}>
                ⚠ Semantic index: {searchMeta.embedded_count}/{searchMeta.total} transactions indexed (still embedding…)
              </span>
            )}
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: 12, marginBottom: 20, alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 4, background: "#f3f4f6", borderRadius: 8, padding: 3 }}>
          {(["spending", "refunds", "all"] as const).map((t) => (
            <button key={t} onClick={() => setTxType(t)} style={{
              padding: "5px 10px", borderRadius: 6, fontSize: 12, border: "none", cursor: "pointer",
              background: txType === t ? (t === "refunds" ? "#10b981" : "#287c61") : "transparent",
              color: txType === t ? "#fff" : "#6b7280",
              fontWeight: txType === t ? 600 : 400,
              textTransform: "capitalize",
            }}>{t}</button>
          ))}
        </div>
        <select aria-label="Category" value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)}
          style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #ddd", fontSize: 14 }}>
          <option value="">All Categories</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select aria-label="Bank" value={filterSource} onChange={(e) => setFilterSource(e.target.value)}
          style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #ddd", fontSize: 14 }}>
          <option value="">All Banks</option>
          <option value="chase">Chase</option>
          <option value="discover">Discover</option>
          <option value="amex">Amex</option>
        </select>
        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
          title="From date" aria-label="From date"
          style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid #ddd", fontSize: 14, color: dateFrom ? "#111" : "#9ca3af" }} />
        <span style={{ color: "#9ca3af", fontSize: 13 }}>—</span>
        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
          title="To date" aria-label="To date"
          style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid #ddd", fontSize: 14, color: dateTo ? "#111" : "#9ca3af" }} />
        {filterMonth && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, background: "#287c61", color: "#fff", padding: "5px 12px", borderRadius: 20, fontSize: 13 }}>
            <span>{filterMonth}</span>
            <span onClick={() => navigate("/transactions")} style={{ cursor: "pointer", fontWeight: 700, fontSize: 16, lineHeight: 1 }}>×</span>
          </div>
        )}
        {filterMerchant && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, background: "#10b981", color: "#fff", padding: "5px 12px", borderRadius: 20, fontSize: 13 }}>
            <span>🏪 {filterMerchant}</span>
            <span onClick={() => navigate("/transactions")} style={{ cursor: "pointer", fontWeight: 700, fontSize: 16, lineHeight: 1 }}>×</span>
          </div>
        )}
        {txs.length > 0 && (
          <span style={{ color: "#9ca3af", fontSize: 13, marginLeft: "auto" }}>{searchQuery.trim() ? `${searchMeta?.total_results ?? txs.length} matching` : txs.length} transactions</span>
        )}
        {txs.length > 0 && (
          <button disabled={isSearching || pending || invalidRange || exporting} onClick={handleExport} style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #ddd", cursor: exporting ? "wait" : "pointer" }}>{exporting ? "Preparing CSV…" : "↓ CSV"}</button>
        )}
        <button onClick={clearFilters} style={{ border: 0, background: "transparent", color: "#6d5bd0", cursor: "pointer" }}>Clear filters</button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12, marginBottom: 20 }}>
        {([
          ["description", "Description", "Contains text…"], ["merchant_contains", "Merchant", "Merchant name…"],
          ["city", "City", "City name…"], ["merchant_type", "Merchant type", "e.g. grocery store"],
          ["min_amount", "Min amount ($)", "0.00"], ["max_amount", "Max amount ($)", "No maximum"],
        ] as const).map(([key, label, placeholder]) => (
          <label key={key} style={{ display: "grid", gap: 5, fontSize: 12, color: "#6b7280" }}>
            {label}
            <input type={key.includes("amount") ? "number" : "text"} min={key.includes("amount") ? 0 : undefined} step={key.includes("amount") ? "0.01" : undefined}
              value={columns[key] ?? ""} placeholder={placeholder}
              onChange={e => setColumns(prev => ({ ...prev, [key]: e.target.value }))}
              style={{ width: "100%", boxSizing: "border-box", padding: "8px 10px", border: "1px solid #ddd", borderRadius: 6, fontSize: 13 }} />
          </label>
        ))}
        {([["is_online", "Online", "Online", "In person"], ["is_subscription", "Recurring", "Recurring", "Not recurring"]] as const).map(([key, label, yes, no]) => (
          <label key={key} style={{ display: "grid", gap: 5, fontSize: 12, color: "#6b7280" }}>
            {label}
            <select value={columns[key] ?? ""} onChange={e => setColumns(prev => ({ ...prev, [key]: e.target.value }))}
              style={{ padding: "8px 10px", border: "1px solid #ddd", borderRadius: 6, fontSize: 13 }}>
              <option value="">All</option><option value="true">{yes}</option><option value="false">{no}</option>
            </select>
          </label>
        ))}
      </div>
      <div role="status" style={{ marginBottom: 12, fontSize: 13, color: invalidRange || loadError ? "#b91c1c" : "#6b7280" }}>
        {invalidRange ? "Check your ranges: minimum must not exceed maximum, and From must not be after To." : loadError || ((isSearching || pending) ? "Loading transactions…" : `${searchQuery.trim() ? searchMeta?.total_results ?? txs.length : txs.length} matching transactions`)}
      </div>
      {exportError && <div role="alert" style={{ color: "#b91c1c", marginBottom: 12 }}>{exportError}</div>}
      {searchQuery.trim() && searchMeta && searchMeta.total_results > SEARCH_PAGE_SIZE && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10, margin: "0 0 12px" }}>
          <span style={{ color: "#6b7280", fontSize: 12 }}>Page {searchPage + 1} of {Math.ceil(searchMeta.total_results / SEARCH_PAGE_SIZE)}</span>
          <button type="button" onClick={() => setSearchPage((page) => Math.max(0, page - 1))} disabled={searchPage === 0 || isSearching || pending}>← Previous</button>
          <button type="button" onClick={() => setSearchPage((page) => page + 1)} disabled={(searchPage + 1) * SEARCH_PAGE_SIZE >= searchMeta.total_results || isSearching || pending}>Next →</button>
        </div>
      )}
      {deleteError && <div role="alert" style={{ color: "#b91c1c", fontSize: 13, marginBottom: 12 }}>{deleteError}</div>}

      <div role="status" aria-live="polite" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px 16px", marginBottom: 12, padding: "12px 16px", border: "1px solid #dce9dc", borderRadius: 10, background: "#f2f8ef", color: "#284d3b", fontSize: 13 }}>
        <strong>{selectedCount.toLocaleString()} selected</strong>
        <span>Signed total: <strong>{new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(selectedTotal)}</strong></span>
        <span style={{ color: "#5d7568", fontSize: 12 }}>Includes selections hidden by filters or on other pages. Negative amounts subtract.</span>
        {selectedCount > 0 && <button type="button" disabled={bulkSaving} onClick={() => setSelected({})} style={{ marginLeft: "auto", border: "1px solid #cbdcc8", borderRadius: 7, background: "#fff", color: "#285b44", padding: "5px 10px" }}>Clear selection</button>}
        {selectedCount > 0 && <><label htmlFor="bulk-category">Change category</label><select id="bulk-category" value={bulkCategory} disabled={bulkSaving} onChange={(event) => setBulkCategory(event.target.value)}><option value="">Choose category</option>{CATEGORIES.map((category) => <option key={category} value={category}>{category}</option>)}</select><button type="button" disabled={!bulkCategory || bulkSaving} onClick={() => void applyBulkCategory()}>{bulkSaving ? "Updating…" : `Apply to ${selectedCount} selected`}</button></>}
      </div>
      {bulkMessage && <div role="status" style={{ marginBottom: 12, color: "#315f49", fontSize: 13 }}>{bulkMessage}</div>}

      <div style={{ background: "#fff", borderRadius: 10, boxShadow: "0 1px 4px rgba(0,0,0,0.07)", overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ background: "#f0f0f8", textAlign: "left" }}>
              <th style={{ padding: "12px 16px" }}><input type="checkbox" aria-label="Select all transactions shown" checked={allVisibleSelected} disabled={sortedTxs.length === 0 || pending || invalidRange || isSearching || bulkSaving}
                ref={(element) => { if (element) element.indeterminate = selectedVisibleCount > 0 && !allVisibleSelected; }}
                onChange={(event) => setSelected((current) => toggleVisibleSelection(current, sortedTxs, event.target.checked))} /></th>
              <th aria-sort={sortField === "date" ? (sortDir === "asc" ? "ascending" : "descending") : "none"} style={{ padding: "12px 16px", whiteSpace: "nowrap" }}>
                <button onClick={() => toggleSort("date")} style={{ border: 0, background: "transparent", font: "inherit", fontWeight: 600, cursor: "pointer", padding: 0 }}>Date {sortField === "date" ? (sortDir === "desc" ? "↓" : "↑") : <span style={{ color: "#9ca3af" }}>↕</span>}</button>
              </th>
              <th style={{ padding: "12px 16px" }}><button onClick={() => toggleSort("description")} style={{ border: 0, background: "transparent", font: "inherit", fontWeight: 600, cursor: "pointer" }}>Description {sortField === "description" ? (sortDir === "asc" ? "↑" : "↓") : "↕"}</button></th>
              <th style={{ padding: "12px 16px" }}><button onClick={() => toggleSort("source")} style={{ border: 0, background: "transparent", font: "inherit", fontWeight: 600, cursor: "pointer" }}>Bank {sortField === "source" ? (sortDir === "asc" ? "↑" : "↓") : "↕"}</button></th>
              <th style={{ padding: "12px 16px" }}><button onClick={() => toggleSort("category")} style={{ border: 0, background: "transparent", font: "inherit", fontWeight: 600, cursor: "pointer" }}>Category {sortField === "category" ? (sortDir === "asc" ? "↑" : "↓") : "↕"}</button></th>
              <th aria-sort={sortField === "amount" ? (sortDir === "asc" ? "ascending" : "descending") : "none"} style={{ padding: "12px 16px", textAlign: "right", whiteSpace: "nowrap" }}>
                <button onClick={() => toggleSort("amount")} style={{ border: 0, background: "transparent", font: "inherit", fontWeight: 600, cursor: "pointer", padding: 0 }}>Amount {sortField === "amount" ? (sortDir === "desc" ? "↓" : "↑") : <span style={{ color: "#9ca3af" }}>↕</span>}</button>
              </th>
              <th style={{ padding: "12px 16px", whiteSpace: "nowrap" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {sortedTxs.map((tx) => {
              const isExpanded = expandedId === tx.id;
              const isRefund = tx.amount < 0;
              return (
                <Fragment key={tx.id}>
                  <tr
                    key={tx.id}
                    style={{ borderTop: "1px solid #f0f0f0", cursor: "pointer", background: isExpanded ? "#f9fafb" : isRefund ? "#f0fdf4" : undefined }}
                    onClick={() => setExpandedId(isExpanded ? null : tx.id)}
                  >
                    <td style={{ padding: "10px 16px" }} onClick={(event) => event.stopPropagation()}><input type="checkbox" aria-label={`Select ${tx.description} on ${tx.date}`} checked={!!selected[tx.id]} disabled={pending || invalidRange || isSearching || bulkSaving}
                      onChange={(event) => setSelected((current) => toggleVisibleSelection(current, [tx], event.target.checked))} /></td>
                    <td style={{ padding: "10px 16px", color: "#888" }}>{tx.date}</td>
                    <td style={{ padding: "10px 16px" }}>
                      {tx.description}
                      {tx.merchant_name && tx.merchant_name !== tx.description && (
                        <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 2 }}>{tx.merchant_name}</div>
                      )}
                    </td>
                    <td style={{ padding: "10px 16px", color: "#888", textTransform: "capitalize" }}>
                      {tx.source}
                      {tx.match_type && (
                        <span style={{ marginLeft: 6, fontSize: 10, padding: "1px 5px", borderRadius: 8,
                          background: tx.match_type === "both" ? "#d1fae5" : tx.match_type === "semantic" ? "#ede9fe" : "#dbeafe",
                          color: tx.match_type === "both" ? "#065f46" : tx.match_type === "semantic" ? "#5b21b6" : "#1e40af",
                        }}>{tx.match_type}</span>
                      )}
                    </td>
                    <td style={{ padding: "10px 16px" }} onClick={(e) => e.stopPropagation()}>
                      {editingId === tx.id ? (
                        <select autoFocus defaultValue={tx.category}
                          onChange={(e) => handleCategoryChange(tx.id, e.target.value)}
                          onBlur={() => setEditingId(null)}
                          style={{ fontSize: 13, padding: "2px 6px", borderRadius: 4 }}>
                          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                        </select>
                      ) : (
                        <span onClick={() => setEditingId(tx.id)} style={{
                          background: CATEGORY_COLORS[tx.category] ?? "#d1d5db",
                          color: "#fff", padding: "2px 8px", borderRadius: 12,
                          fontSize: 12, cursor: "pointer",
                        }}>{tx.category ?? "—"}</span>
                      )}
                    </td>
                    <td style={{ padding: "10px 16px", textAlign: "right", color: tx.amount < 0 ? "#e05" : "#0a0", fontWeight: 600 }}>
                      {tx.amount < 0 ? "-" : "+"}${Math.abs(tx.amount).toFixed(2)}
                    </td>
                    <td style={{ padding: "10px 16px" }} onClick={(event) => event.stopPropagation()}>
                      <button type="button" aria-label={`Delete ${tx.description} on ${tx.date}`}
                        disabled={deletingId !== null} onClick={() => void handleDelete(tx)}
                        style={{ border: "1px solid #fecaca", borderRadius: 6, background: "#fff", color: "#b91c1c", padding: "5px 9px", cursor: deletingId ? "wait" : "pointer", opacity: deletingId ? 0.65 : 1 }}>
                        {deletingId === tx.id ? "Deleting…" : "Delete"}
                      </button>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr key={`${tx.id}-detail`} style={{ background: "#f9fafb" }}>
                      <td colSpan={7} style={{ padding: "10px 24px 14px", borderTop: "1px solid #e5e7eb" }} onClick={(event) => event.stopPropagation()}>
                        <div style={{ display: "flex", gap: 32, flexWrap: "wrap", fontSize: 13, color: "#4b5563" }}>
                          <div><span style={{ color: "#9ca3af" }}>Merchant</span><br /><strong>{tx.merchant_name || "Unknown"}</strong></div>
                          <div><span style={{ color: "#9ca3af" }}>Type</span><br /><strong>{tx.merchant_type || "Unknown"}</strong></div>
                          <div><span style={{ color: "#9ca3af" }}>City</span><br /><strong>{tx.city || "Unknown"}</strong></div>
                          <div><span style={{ color: "#9ca3af" }}>Online</span><br /><strong>{tx.is_online === true ? "Yes" : tx.is_online === false ? "No" : "Unknown"}</strong></div>
                          {tx.is_subscription && (
                            <div><span style={{ color: "#9ca3af" }}>Recurring</span><br /><strong style={{ color: "#287c61" }}>Yes</strong></div>
                          )}
                          <div><span style={{ color: "#9ca3af" }}>ID</span><br /><span style={{ fontFamily: "monospace", fontSize: 11, color: "#9ca3af" }}>{tx.id}</span></div>
                        </div>
                        <div style={{ marginTop: 12 }}>
                          <button type="button" onClick={() => void loadProvenance(tx.id)} disabled={provenance?.id === tx.id && provenance.loading} style={{ border: "1px solid #c9dacb", borderRadius: 6, background: "#fff", color: "#285b44", padding: "6px 11px", cursor: "pointer", marginBottom: 10 }}>View import & AI history</button>
                          {provenance?.id === tx.id && <div style={{ marginBottom: 12, padding: 12, borderRadius: 8, background: "#eef6ed", fontSize: 12, color: "#36584a" }}>
                            {provenance.loading ? "Loading history…" : provenance.error ? <span role="alert">{provenance.error}</span> : provenance.data && <>
                              <p style={{ margin: "0 0 6px" }}>Category: {provenance.data.manual_category ? "Manually set and protected from AI re-categorization" : "No manual category override recorded"}.</p>
                              {provenance.data.imports.length ? provenance.data.imports.map((entry, index) => <p key={`${entry.filename}-${entry.row_number}-${index}`} style={{ margin: "4px 0" }}>Imported from {entry.filename}, row {entry.row_number} · {new Date(entry.imported_at).toLocaleDateString()}</p>) : <p style={{ margin: "4px 0" }}>No import file record is available for this transaction.</p>}
                              {provenance.data.enrichment_history.map((entry, index) => <p key={`${entry.updated_at}-${index}`} style={{ margin: "4px 0" }}>{entry.mode === "recategorize" ? "Re-categorization" : "Enrichment"}: {entry.status}{entry.model ? ` · ${entry.model}` : ""} · {new Date(entry.updated_at).toLocaleDateString()}</p>)}
                              <p style={{ margin: "6px 0 0", color: "#667a6d" }}>{provenance.data.note}</p>
                            </>}
                          </div>}
                          {detailsEditorId === tx.id ? <>
                            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 8, maxWidth: 760 }}>
                              <label style={{ display: "grid", gap: 4, fontSize: 12, color: "#6b7280" }}>Merchant<input aria-label="Correct merchant" value={detailsDraft.merchant_name} onChange={(event) => setDetailsDraft((draft) => ({ ...draft, merchant_name: event.target.value }))} style={{ padding: "7px 9px", border: "1px solid #d1d5db", borderRadius: 6 }} /></label>
                              <label style={{ display: "grid", gap: 4, fontSize: 12, color: "#6b7280" }}>City<input aria-label="Correct city" value={detailsDraft.city} onChange={(event) => setDetailsDraft((draft) => ({ ...draft, city: event.target.value }))} style={{ padding: "7px 9px", border: "1px solid #d1d5db", borderRadius: 6 }} /></label>
                              <label style={{ display: "grid", gap: 4, fontSize: 12, color: "#6b7280" }}>Merchant type<input aria-label="Correct merchant type" value={detailsDraft.merchant_type} onChange={(event) => setDetailsDraft((draft) => ({ ...draft, merchant_type: event.target.value }))} style={{ padding: "7px 9px", border: "1px solid #d1d5db", borderRadius: 6 }} /></label>
                              <label style={{ display: "grid", gap: 4, fontSize: 12, color: "#6b7280" }}>Online status<select aria-label="Online status" value={detailsDraft.is_online} onChange={(event) => setDetailsDraft((draft) => ({ ...draft, is_online: event.target.value }))} style={{ padding: "7px 9px", border: "1px solid #d1d5db", borderRadius: 6 }}><option value="unknown">Unknown</option><option value="true">Yes</option><option value="false">No</option></select></label>
                            </div>
                            {detailsError && <div role="alert" style={{ color: "#b91c1c", fontSize: 12, marginTop: 7 }}>{detailsError}</div>}
                            <div style={{ display: "flex", gap: 8, marginTop: 8 }}><button onClick={() => saveDetails(tx)} disabled={detailsSaving} style={{ border: 0, borderRadius: 6, background: "#287c61", color: "#fff", padding: "6px 12px", cursor: "pointer" }}>{detailsSaving ? "Saving…" : "Save details"}</button><button onClick={() => setDetailsEditorId(null)} disabled={detailsSaving} style={{ border: "1px solid #d1d5db", borderRadius: 6, background: "#fff", padding: "6px 12px", cursor: "pointer" }}>Cancel</button></div>
                          </> : <button onClick={() => startDetailsEdit(tx)} style={{ border: "1px solid #d1d5db", borderRadius: 6, background: "#fff", color: "#4b5563", padding: "6px 11px", cursor: "pointer" }}>Edit merchant, city, or type</button>}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
        {txs.length === 0 && (
          <p style={{ textAlign: "center", color: "#aaa", padding: 40 }}>No transactions match these filters. Try a wider range or clear filters.</p>
        )}
      </div>
    </div>
  );
}
