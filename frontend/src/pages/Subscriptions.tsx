import { Fragment, useEffect, useState } from "react";
import { getSubscriptions, updateSubscription, redetectSubscriptions, createSubscription, deleteSubscription } from "../api/client";
import type { SubscriptionRecord } from "../api/client";

export function Subscriptions() {
  const [subs, setSubs] = useState<SubscriptionRecord[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [redetecting, setRedetecting] = useState(false);
  const [redetectError, setRedetectError] = useState("");
  const [redetectMessage, setRedetectMessage] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState("");
  const [newAmount, setNewAmount] = useState("");
  const [newFreq, setNewFreq] = useState("monthly");

  useEffect(() => { getSubscriptions().then(setSubs); }, []);

  const handleRedetect = async () => {
    setRedetecting(true);
    setRedetectError("");
    setRedetectMessage("");
    try {
      await redetectSubscriptions();
      const fresh = await getSubscriptions();
      setSubs(fresh);
      setRedetectMessage("Recurring charges refreshed.");
    } catch {
      setRedetectError("Could not refresh recurring charges. Check that the finance API is running, then try again.");
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
    const amount = parseFloat(newAmount);
    setSubs((prev) => [...prev, { ...sub, last_charged: sub.last_charged ?? null, origin: "manual", dismissed: false,
      amount_type: "fixed", average_monthly_amount: newFreq === "monthly" ? amount : amount / 12,
      latest_charge_amount: amount, latest_period_amount: amount, supporting_transactions: [] }]);
    setNewName(""); setNewAmount(""); setNewFreq("monthly"); setShowAdd(false);
  };

  const handleDelete = async (id: string) => {
    await deleteSubscription(id);
    setSubs((prev) => prev.filter((s) => s.id !== id));
  };

  const active = subs.filter((s) => s.active);
  const inactive = subs.filter((s) => !s.active);
  const monthlyEquivalent = (sub: SubscriptionRecord) => sub.origin !== "detected"
    ? sub.amount / (sub.frequency === "annual" ? 12 : 1)
    : sub.average_monthly_amount;
  const fixedPeriodAmount = (sub: SubscriptionRecord) => sub.origin !== "detected"
    ? sub.amount
    : sub.latest_period_amount || (sub.frequency === "annual" ? sub.average_monthly_amount * 12 : sub.average_monthly_amount);
  const monthlyTotal = active.reduce((sum, sub) => sum + monthlyEquivalent(sub), 0);
  const annualTotal = monthlyTotal * 12;
  const fixedSubs = (rows: SubscriptionRecord[]) => rows.filter((sub) => sub.amount_type !== "variable");
  const variableSubs = (rows: SubscriptionRecord[]) => rows.filter((sub) => sub.amount_type === "variable");

  const renderTable = (title: string, rows: SubscriptionRecord[], variable: boolean) => (
    <section style={{ background: "#fff", borderRadius: 10, boxShadow: "0 1px 4px rgba(0,0,0,0.07)", overflow: "hidden", marginBottom: 20 }}>
      <div style={{ padding: "16px 18px 10px" }}>
        <h2 style={{ margin: 0, fontSize: 17 }}>{title}</h2>
        <p style={{ margin: "5px 0 0", color: "#788397", fontSize: 12 }}>
          {variable ? "Likely automatic bills with changing amounts. Average uses up to six complete months with observed charges." : "Likely automatic bills with stable charge amounts."}
        </p>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead><tr style={{ background: "#f0f0f8", textAlign: "left" }}>
            <th style={{ padding: "12px 16px" }}>Service</th>
            <th style={{ padding: "12px 16px" }}>Frequency</th>
            <th style={{ padding: "12px 16px" }}>Last Charged</th>
            <th style={{ padding: "12px 16px", textAlign: "right" }}>{variable ? "Average / Latest" : "Amount"}</th>
            <th style={{ padding: "12px 16px", textAlign: "center" }}>Active</th>
            <th style={{ padding: "12px 16px" }}></th>
          </tr></thead>
          <tbody>
            {rows.map((sub) => <Fragment key={sub.id}>
              <tr style={{ borderTop: "1px solid #e5e9f0", background: sub.active ? "#fff" : "#fafbfc" }}>
                <td style={{ padding: "10px 16px", fontWeight: 500 }}>
                  <div>{sub.description}</div>
                  <span className={`subscription-origin subscription-origin-${sub.origin}`}>
                    {sub.origin === "detected" ? "Auto-detected" : sub.origin === "manual" ? "Manually added" : "Legacy entry"}
                  </span>
                  {sub.supporting_transactions.length > 0 && <button type="button" className="subscription-evidence-toggle"
                    aria-expanded={expanded === sub.id} onClick={() => setExpanded((current) => current === sub.id ? null : sub.id)}>
                    {expanded === sub.id ? "Hide" : "View"} {sub.supporting_transactions.length} supporting transaction{sub.supporting_transactions.length === 1 ? "" : "s"}
                  </button>}
                </td>
                <td style={{ padding: "10px 16px", color: "#788397", textTransform: "capitalize" }}>{sub.frequency}</td>
                <td style={{ padding: "10px 16px", color: "#788397" }}>{sub.last_charged ?? "—"}</td>
                <td style={{ padding: "10px 16px", textAlign: "right" }}>
                  {variable ? <><strong>${monthlyEquivalent(sub).toFixed(2)} avg/mo</strong>
                    <div style={{ color: "#788397", fontSize: 12 }}>Latest period ${sub.latest_period_amount.toFixed(2)}</div></>
                    : <strong>${fixedPeriodAmount(sub).toFixed(2)} / {sub.frequency === "annual" ? "year" : "month"}</strong>}
                </td>
                <td style={{ padding: "10px 16px", textAlign: "center" }}>
                  <input type="checkbox" aria-label={`${sub.active ? "Deactivate" : "Activate"} ${sub.description}`} checked={sub.active} onChange={() => toggleActive(sub.id, sub.active)} />
                </td>
                <td style={{ padding: "10px 16px", textAlign: "center" }}>
                  <button onClick={() => handleDelete(sub.id)} title="Delete" aria-label={`Delete ${sub.description}`} style={{ background: "none", border: "none", cursor: "pointer", color: "#738094", fontSize: 16 }}>🗑</button>
                </td>
              </tr>
              {expanded === sub.id && <tr className="subscription-evidence-row"><td colSpan={6}>
                <div className="subscription-evidence-list">
                  {sub.supporting_transactions.map((tx) => <div key={tx.id} className="subscription-evidence-item">
                    <span>{tx.date}</span><strong>{tx.merchant_name || tx.description}</strong>
                    {tx.merchant_name && <span className="subscription-evidence-description">{tx.description}</span>}
                    <span>{tx.source}</span><strong>${Math.abs(tx.amount).toFixed(2)}</strong>
                  </div>)}
                </div>
              </td></tr>}
            </Fragment>)}
            {rows.length === 0 && <tr><td colSpan={6} style={{ textAlign: "center", color: "#8a94a6", padding: 22 }}>
              No {variable ? "variable" : "fixed"} charges in this section.
            </td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );

  const renderStatusSection = (title: string, rows: SubscriptionRecord[], isActive: boolean) => (
    <section className={`subscription-status-section ${isActive ? "is-active" : "is-inactive"}`}>
      <header className="subscription-status-header">
        <div>
          <h2>{title}</h2>
          <p>{isActive
            ? "Included in the estimated monthly and annual totals."
            : "Excluded from totals. Charges may be paused or not seen recently; switch one on to count it again."}</p>
        </div>
        <span className="subscription-status-count">{rows.length} {rows.length === 1 ? "charge" : "charges"}</span>
      </header>
      <div className="subscription-status-tables">
        {renderTable("Fixed recurring charges", fixedSubs(rows), false)}
        {renderTable("Variable recurring charges", variableSubs(rows), true)}
      </div>
    </section>
  );

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <h1 style={{ fontSize: 24, margin: 0 }}>Bills & subscriptions</h1>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => setShowAdd((v) => !v)} style={{
            background: "#10b981", color: "#fff", border: "none",
            borderRadius: 8, padding: "7px 16px", cursor: "pointer", fontSize: 13,
          }}>+ Add</button>
          <button onClick={handleRedetect} disabled={redetecting} style={{
            background: "#287c61", color: "#fff", border: "none",
            borderRadius: 8, padding: "7px 16px", cursor: "pointer", fontSize: 13,
          }}>
            {redetecting ? "Detecting…" : "Re-detect"}
          </button>
        </div>
      </div>
      <p style={{ color: "#888", marginBottom: 16 }}>Auto-detected subscriptions and recurring bills</p>
      {redetectMessage && <p role="status" style={{ color: "#23704c", margin: "-6px 0 16px", fontSize: 13 }}>{redetectMessage}</p>}
      {redetectError && <p role="alert" style={{ color: "#a43e33", margin: "-6px 0 16px", fontSize: 13 }}>{redetectError}</p>}

      <div style={{ display: "flex", gap: 16, marginBottom: 28 }}>
        <div style={{ background: "#fff", borderRadius: 10, padding: "14px 20px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
          <div style={{ color: "#888", fontSize: 12 }}>Active monthly total</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>${monthlyTotal.toFixed(2)}</div>
        </div>
        <div style={{ background: "#fff", borderRadius: 10, padding: "14px 20px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
          <div style={{ color: "#888", fontSize: 12 }}>Active annual total</div>
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

      {renderStatusSection("Active recurring charges", active, true)}
      {renderStatusSection("Inactive or not recently observed", inactive, false)}
    </div>
  );
}
