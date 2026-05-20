import { useEffect, useRef, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { getTransactions, updateTransactionCategory, searchTransactions } from "../api/client";

const CATEGORIES = [
  "dining", "groceries", "transport", "shopping", "entertainment",
  "subscriptions", "health", "travel", "utilities", "other",
];

const CATEGORY_COLORS: Record<string, string> = {
  dining: "#7c6af7", groceries: "#a78bfa", transport: "#c4b5fd",
  shopping: "#60a5fa", entertainment: "#34d399", subscriptions: "#f59e0b",
  health: "#f87171", travel: "#38bdf8", utilities: "#94a3b8", other: "#d1d5db",
};

export function Transactions() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [txs, setTxs] = useState<any[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filterCategory, setFilterCategory] = useState("");
  const [filterSource, setFilterSource] = useState("");
  const [txType, setTxType] = useState<"spending" | "refunds">("spending");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sortField, setSortField] = useState<"date" | "amount">("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMode, setSearchMode] = useState<"hybrid" | "keyword" | "semantic">("hybrid");
  const [searchMeta, setSearchMeta] = useState<{ embedded_count?: number; total?: number } | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const filterMonth = searchParams.get("month") ?? "";
  const filterMerchant = searchParams.get("merchant") ?? "";
  const filterQ = searchParams.get("q") ?? "";
  const filterIds = searchParams.get("ids") ?? "";
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Pre-populate search from URL ?q= param
  useEffect(() => {
    if (filterQ) setSearchQuery(filterQ);
  }, [filterQ]);

  // Load transactions (when no search query)
  useEffect(() => {
    if (searchQuery) return;
    getTransactions({
      category: filterCategory || undefined,
      source: filterSource || undefined,
      month: filterMonth || undefined,
      merchant: filterMerchant || undefined,
      tx_type: txType,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      ids: filterIds || undefined,
    }).then(setTxs);
  }, [filterCategory, filterSource, filterMonth, filterMerchant, searchQuery, txType, dateFrom, dateTo, filterIds]);

  // Debounced search
  useEffect(() => {
    if (!searchQuery.trim()) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setIsSearching(true);
      try {
        const data = await searchTransactions(searchQuery, searchMode);
        setTxs(data.results);
        setSearchMeta({ embedded_count: data.embedded_count, total: data.total_transactions });
      } finally {
        setIsSearching(false);
      }
    }, 350);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [searchQuery, searchMode]);

  const handleCategoryChange = async (id: string, category: string) => {
    await updateTransactionCategory(id, category);
    setTxs((prev) => prev.map((tx) => tx.id === id ? { ...tx, category } : tx));
    setEditingId(null);
  };

  const toggleSort = (field: "date" | "amount") => {
    if (sortField === field) setSortDir((d) => d === "asc" ? "desc" : "asc");
    else { setSortField(field); setSortDir("desc"); }
  };

  const sortedTxs = [...txs].sort((a, b) => {
    const mul = sortDir === "asc" ? 1 : -1;
    if (sortField === "amount") return mul * (a.amount - b.amount);
    return mul * (a.date < b.date ? -1 : a.date > b.date ? 1 : 0);
  });

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
              onFocus={(e) => e.target.style.borderColor = "#7c6af7"}
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
                background: searchMode === m ? "#7c6af7" : "transparent",
                color: searchMode === m ? "#fff" : "#6b7280",
                fontWeight: searchMode === m ? 600 : 400,
              }}>{m}</button>
            ))}
          </div>
        </div>
        {searchQuery && searchMeta && (
          <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 6 }}>
            {isSearching ? "Searching…" : `${txs.length} results`}
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
          {(["spending", "refunds"] as const).map((t) => (
            <button key={t} onClick={() => setTxType(t)} style={{
              padding: "5px 10px", borderRadius: 6, fontSize: 12, border: "none", cursor: "pointer",
              background: txType === t ? (t === "refunds" ? "#10b981" : "#7c6af7") : "transparent",
              color: txType === t ? "#fff" : "#6b7280",
              fontWeight: txType === t ? 600 : 400,
              textTransform: "capitalize",
            }}>{t}</button>
          ))}
        </div>
        <select value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)}
          style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #ddd", fontSize: 14 }}>
          <option value="">All Categories</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={filterSource} onChange={(e) => setFilterSource(e.target.value)}
          style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #ddd", fontSize: 14 }}>
          <option value="">All Banks</option>
          <option value="chase">Chase</option>
          <option value="discover">Discover</option>
          <option value="amex">Amex</option>
        </select>
        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
          title="From date"
          style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid #ddd", fontSize: 14, color: dateFrom ? "#111" : "#9ca3af" }} />
        <span style={{ color: "#9ca3af", fontSize: 13 }}>—</span>
        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
          title="To date"
          style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid #ddd", fontSize: 14, color: dateTo ? "#111" : "#9ca3af" }} />
        {filterMonth && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, background: "#7c6af7", color: "#fff", padding: "5px 12px", borderRadius: 20, fontSize: 13 }}>
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
          <span style={{ color: "#9ca3af", fontSize: 13, marginLeft: "auto" }}>{txs.length} transactions</span>
        )}
        {txs.length > 0 && (
          <a href={(() => {
            const p = new URLSearchParams();
            if (filterCategory) p.set("category", filterCategory);
            if (filterSource) p.set("source", filterSource);
            if (filterMonth) p.set("month", filterMonth);
            if (filterMerchant) p.set("merchant", filterMerchant);
            if (dateFrom) p.set("date_from", dateFrom);
            if (dateTo) p.set("date_to", dateTo);
            p.set("tx_type", txType);
            return `http://localhost:8000/transactions/export.csv?${p.toString()}`;
          })()} download="transactions.csv"
            style={{ background: "#f3f4f6", color: "#374151", borderRadius: 6, padding: "5px 12px", fontSize: 12, textDecoration: "none", border: "1px solid #e5e7eb" }}>
            ↓ CSV
          </a>
        )}
      </div>

      <div style={{ background: "#fff", borderRadius: 10, boxShadow: "0 1px 4px rgba(0,0,0,0.07)", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ background: "#f0f0f8", textAlign: "left" }}>
              <th onClick={() => toggleSort("date")} style={{ padding: "12px 16px", cursor: "pointer", userSelect: "none", whiteSpace: "nowrap" }}>
                Date {sortField === "date" ? (sortDir === "desc" ? "↓" : "↑") : <span style={{ color: "#c4c4d4" }}>↕</span>}
              </th>
              <th style={{ padding: "12px 16px" }}>Description</th>
              <th style={{ padding: "12px 16px" }}>Bank</th>
              <th style={{ padding: "12px 16px" }}>Category</th>
              <th onClick={() => toggleSort("amount")} style={{ padding: "12px 16px", textAlign: "right", cursor: "pointer", userSelect: "none", whiteSpace: "nowrap" }}>
                Amount {sortField === "amount" ? (sortDir === "desc" ? "↓" : "↑") : <span style={{ color: "#c4c4d4" }}>↕</span>}
              </th>
            </tr>
          </thead>
          <tbody>
            {sortedTxs.map((tx) => {
              const isExpanded = expandedId === tx.id;
              const isRefund = tx.amount < 0;
              return (
                <>
                  <tr
                    key={tx.id}
                    style={{ borderTop: "1px solid #f0f0f0", cursor: "pointer", background: isExpanded ? "#f9fafb" : isRefund ? "#f0fdf4" : undefined }}
                    onClick={() => setExpandedId(isExpanded ? null : tx.id)}
                  >
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
                  </tr>
                  {isExpanded && (
                    <tr key={`${tx.id}-detail`} style={{ background: "#f9fafb" }}>
                      <td colSpan={5} style={{ padding: "10px 24px 14px", borderTop: "1px solid #e5e7eb" }}>
                        <div style={{ display: "flex", gap: 32, fontSize: 13, color: "#4b5563" }}>
                          {tx.merchant_name && (
                            <div><span style={{ color: "#9ca3af" }}>Merchant</span><br /><strong>{tx.merchant_name}</strong></div>
                          )}
                          {tx.merchant_type && (
                            <div><span style={{ color: "#9ca3af" }}>Type</span><br /><strong>{tx.merchant_type}</strong></div>
                          )}
                          {tx.city && (
                            <div><span style={{ color: "#9ca3af" }}>City</span><br /><strong>{tx.city}</strong></div>
                          )}
                          <div><span style={{ color: "#9ca3af" }}>Online</span><br /><strong>{tx.is_online ? "Yes" : "No"}</strong></div>
                          {tx.is_subscription && (
                            <div><span style={{ color: "#9ca3af" }}>Recurring</span><br /><strong style={{ color: "#7c6af7" }}>Yes</strong></div>
                          )}
                          <div><span style={{ color: "#9ca3af" }}>ID</span><br /><span style={{ fontFamily: "monospace", fontSize: 11, color: "#9ca3af" }}>{tx.id}</span></div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
        {txs.length === 0 && (
          <p style={{ textAlign: "center", color: "#aaa", padding: 40 }}>No transactions yet. Sync your accounts in Settings.</p>
        )}
      </div>
    </div>
  );
}
