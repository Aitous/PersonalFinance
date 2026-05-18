import { useEffect, useState } from "react";
import { getSubscriptions, updateSubscription } from "../api/client";

export function Subscriptions() {
  const [subs, setSubs] = useState<any[]>([]);

  useEffect(() => { getSubscriptions().then(setSubs); }, []);

  const toggleActive = async (id: string, active: boolean) => {
    await updateSubscription(id, { active: !active });
    setSubs((prev) => prev.map((s) => s.id === id ? { ...s, active: !active } : s));
  };

  const active = subs.filter((s) => s.active);
  const monthlyTotal = active.filter((s) => s.frequency === "monthly").reduce((sum, s) => sum + s.amount, 0);
  const annualTotal = active.reduce((sum, s) => sum + (s.frequency === "monthly" ? s.amount * 12 : s.amount), 0);

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 8 }}>Subscriptions</h1>
      <p style={{ color: "#888", marginBottom: 16 }}>Auto-detected recurring charges</p>

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

      <div style={{ background: "#fff", borderRadius: 10, boxShadow: "0 1px 4px rgba(0,0,0,0.07)", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ background: "#f0f0f8", textAlign: "left" }}>
              <th style={{ padding: "12px 16px" }}>Service</th>
              <th style={{ padding: "12px 16px" }}>Frequency</th>
              <th style={{ padding: "12px 16px" }}>Last Charged</th>
              <th style={{ padding: "12px 16px", textAlign: "right" }}>Amount</th>
              <th style={{ padding: "12px 16px", textAlign: "center" }}>Active</th>
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
