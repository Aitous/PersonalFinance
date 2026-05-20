import { useEffect, useState } from "react";
import { getSubscriptions, updateSubscription, redetectSubscriptions, createSubscription, deleteSubscription } from "../api/client";

export function Subscriptions() {
  const [subs, setSubs] = useState<any[]>([]);
  const [redetecting, setRedetecting] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState("");
  const [newAmount, setNewAmount] = useState("");
  const [newFreq, setNewFreq] = useState("monthly");

  useEffect(() => { getSubscriptions().then(setSubs); }, []);

  const handleRedetect = async () => {
    setRedetecting(true);
    try {
      await redetectSubscriptions();
      const fresh = await getSubscriptions();
      setSubs(fresh);
    } finally {
      setRedetecting(false);
    }
  };

  const toggleActive = async (id: string, active: boolean) => {
    await updateSubscription(id, { active: !active });
    setSubs((prev) => prev.map((s) => s.id === id ? { ...s, active: !active } : s));
  };

  const handleAdd = async () => {
    if (!newName.trim() || !newAmount) return;
    const sub = await createSubscription({ description: newName.trim(), amount: parseFloat(newAmount), frequency: newFreq });
    setSubs((prev) => [...prev, { ...sub, last_charged: sub.last_charged ?? null }]);
    setNewName(""); setNewAmount(""); setNewFreq("monthly"); setShowAdd(false);
  };

  const handleDelete = async (id: string) => {
    await deleteSubscription(id);
    setSubs((prev) => prev.filter((s) => s.id !== id));
  };

  const active = subs.filter((s) => s.active);
  const monthlyTotal = active.filter((s) => s.frequency === "monthly").reduce((sum, s) => sum + s.amount, 0);
  const annualTotal = active.reduce((sum, s) => sum + (s.frequency === "monthly" ? s.amount * 12 : s.amount), 0);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <h1 style={{ fontSize: 24, margin: 0 }}>Recurring Charges</h1>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => setShowAdd((v) => !v)} style={{
            background: "#10b981", color: "#fff", border: "none",
            borderRadius: 8, padding: "7px 16px", cursor: "pointer", fontSize: 13,
          }}>+ Add</button>
          <button onClick={handleRedetect} disabled={redetecting} style={{
            background: "#7c6af7", color: "#fff", border: "none",
            borderRadius: 8, padding: "7px 16px", cursor: "pointer", fontSize: 13,
          }}>
            {redetecting ? "Detecting…" : "Re-detect"}
          </button>
        </div>
      </div>
      <p style={{ color: "#888", marginBottom: 16 }}>Auto-detected subscriptions and recurring bills</p>

      <div style={{ display: "flex", gap: 16, marginBottom: 28 }}>
        <div style={{ background: "#fff", borderRadius: 10, padding: "14px 20px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
          <div style={{ color: "#888", fontSize: 12 }}>Monthly Total</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>${monthlyTotal.toFixed(2)}</div>
        </div>
        <div style={{ background: "#fff", borderRadius: 10, padding: "14px 20px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
          <div style={{ color: "#888", fontSize: 12 }}>Annual Total</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>${annualTotal.toFixed(2)}</div>
        </div>
      </div>

      {showAdd && (
        <div style={{ background: "#fff", borderRadius: 10, padding: "16px 20px", marginBottom: 16, boxShadow: "0 1px 4px rgba(0,0,0,0.07)", display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <label style={{ fontSize: 12, color: "#888" }}>Service name</label>
            <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g. Netflix"
              style={{ padding: "7px 10px", borderRadius: 6, border: "1px solid #ddd", fontSize: 14, width: 180 }} />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <label style={{ fontSize: 12, color: "#888" }}>Amount ($)</label>
            <input type="number" value={newAmount} onChange={(e) => setNewAmount(e.target.value)} placeholder="15.99"
              style={{ padding: "7px 10px", borderRadius: 6, border: "1px solid #ddd", fontSize: 14, width: 100 }} />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <label style={{ fontSize: 12, color: "#888" }}>Frequency</label>
            <select value={newFreq} onChange={(e) => setNewFreq(e.target.value)}
              style={{ padding: "7px 10px", borderRadius: 6, border: "1px solid #ddd", fontSize: 14 }}>
              <option value="monthly">Monthly</option>
              <option value="annual">Annual</option>
            </select>
          </div>
          <button onClick={handleAdd} style={{ background: "#10b981", color: "#fff", border: "none", borderRadius: 8, padding: "8px 18px", cursor: "pointer", fontSize: 14 }}>Save</button>
          <button onClick={() => setShowAdd(false)} style={{ background: "#f3f4f6", color: "#555", border: "none", borderRadius: 8, padding: "8px 14px", cursor: "pointer", fontSize: 14 }}>Cancel</button>
        </div>
      )}

      <div style={{ background: "#fff", borderRadius: 10, boxShadow: "0 1px 4px rgba(0,0,0,0.07)", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ background: "#f0f0f8", textAlign: "left" }}>
              <th style={{ padding: "12px 16px" }}>Service</th>
              <th style={{ padding: "12px 16px" }}>Frequency</th>
              <th style={{ padding: "12px 16px" }}>Last Charged</th>
              <th style={{ padding: "12px 16px", textAlign: "right" }}>Amount</th>
              <th style={{ padding: "12px 16px", textAlign: "center" }}>Active</th>
              <th style={{ padding: "12px 16px" }}></th>
            </tr>
          </thead>
          <tbody>
            {subs.map((sub) => (
              <tr key={sub.id} style={{ borderTop: "1px solid #f0f0f0", opacity: sub.active ? 1 : 0.5 }}>
                <td style={{ padding: "10px 16px", fontWeight: 500 }}>{sub.description}</td>
                <td style={{ padding: "10px 16px", color: "#888", textTransform: "capitalize" }}>{sub.frequency}</td>
                <td style={{ padding: "10px 16px", color: "#888" }}>{sub.last_charged ?? "—"}</td>
                <td style={{ padding: "10px 16px", textAlign: "right", fontWeight: 600 }}>${sub.amount.toFixed(2)}</td>
                <td style={{ padding: "10px 16px", textAlign: "center" }}>
                  <input type="checkbox" checked={sub.active} onChange={() => toggleActive(sub.id, sub.active)} />
                </td>
                <td style={{ padding: "10px 16px", textAlign: "center" }}>
                  <button onClick={() => handleDelete(sub.id)} title="Delete" style={{ background: "none", border: "none", cursor: "pointer", color: "#d1d5db", fontSize: 16 }}>🗑</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {subs.length === 0 && (
          <p style={{ textAlign: "center", color: "#aaa", padding: 40 }}>No subscriptions detected yet. Sync your accounts first.</p>
        )}
      </div>
    </div>
  );
}
