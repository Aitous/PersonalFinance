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
  const [filterCategory, setFilterCategory] = useState("");
  const [filterSource, setFilterSource] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMode, setSearchMode] = useState<"hybrid" | "keyword" | "semantic">("hybrid");
  const [searchMeta, setSearchMeta] = useState<{ embedded_count?: number; total?: number } | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const filterMonth = searchParams.get("month") ?? "";
  const filterQ = searchParams.get("q") ?? "";
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Pre-populate search from URL ?q= param (e.g. clicked from Insights merchant row)
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
    }).then(setTxs);
  }, [filterCategory, filterSource, filterMonth, searchQuery]);

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

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 20 }}>Transactions</h1>

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
        {filterMonth && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, background: "#7c6af7", color: "#fff", padding: "5px 12px", borderRadius: 20, fontSize: 13 }}>
            <span>{filterMonth}</span>
            <span onClick={() => navigate("/transactions")} style={{ cursor: "pointer", fontWeight: 700, fontSize: 16, lineHeight: 1 }}>×</span>
          </div>
        )}
        {txs.length > 0 && (
          <span style={{ color: "#9ca3af", fontSize: 13, marginLeft: "auto" }}>{txs.length} transactions</span>
        )}
      </div>

      <div style={{ background: "#fff", borderRadius: 10, boxShadow: "0 1px 4px rgba(0,0,0,0.07)", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ background: "#f0f0f8", textAlign: "left" }}>
              <th style={{ padding: "12px 16px" }}>Date</th>
              <th style={{ padding: "12px 16px" }}>Description</th>
              <th style={{ padding: "12px 16px" }}>Bank</th>
              <th style={{ padding: "12px 16px" }}>Category</th>
              <th style={{ padding: "12px 16px", textAlign: "right" }}>Amount</th>
            </tr>
          </thead>
          <tbody>
            {txs.map((tx) => (
              <tr key={tx.id} style={{ borderTop: "1px solid #f0f0f0" }}>
                <td style={{ padding: "10px 16px", color: "#888" }}>{tx.date}</td>
                <td style={{ padding: "10px 16px" }}>{tx.description}</td>
                <td style={{ padding: "10px 16px", color: "#888", textTransform: "capitalize" }}>
                  {tx.source}
                  {tx.match_type && (
                    <span style={{ marginLeft: 6, fontSize: 10, padding: "1px 5px", borderRadius: 8,
                      background: tx.match_type === "both" ? "#d1fae5" : tx.match_type === "semantic" ? "#ede9fe" : "#dbeafe",
                      color: tx.match_type === "both" ? "#065f46" : tx.match_type === "semantic" ? "#5b21b6" : "#1e40af",
                    }}>{tx.match_type}</span>
                  )}
                </td>
                <td style={{ padding: "10px 16px" }}>
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
            ))}
          </tbody>
        </table>
        {txs.length === 0 && (
          <p style={{ textAlign: "center", color: "#aaa", padding: 40 }}>No transactions yet. Sync your accounts in Settings.</p>
        )}
      </div>
    </div>
  );
}
