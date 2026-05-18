import { useEffect, useState } from "react";
import { getTransactions, updateTransactionCategory } from "../api/client";

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
  const [txs, setTxs] = useState<any[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [filterCategory, setFilterCategory] = useState("");
  const [filterSource, setFilterSource] = useState("");

  useEffect(() => {
    const params: Record<string, string> = {};
    if (filterCategory) params.category = filterCategory;
    if (filterSource) params.source = filterSource;
    getTransactions(params).then(setTxs);
  }, [filterCategory, filterSource]);

  const handleCategoryChange = async (id: string, category: string) => {
    await updateTransactionCategory(id, category);
    setTxs((prev) => prev.map((tx) => tx.id === id ? { ...tx, category } : tx));
    setEditingId(null);
  };

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 20 }}>Transactions</h1>

      <div style={{ display: "flex", gap: 12, marginBottom: 20 }}>
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
                <td style={{ padding: "10px 16px", color: "#888", textTransform: "capitalize" }}>{tx.source}</td>
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
