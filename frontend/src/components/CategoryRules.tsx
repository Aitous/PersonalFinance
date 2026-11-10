import { useEffect, useState } from "react";
import { getCategoryRules, saveCategoryRule, setCategoryRuleEnabled } from "../api/client";
import type { CategoryRule } from "../api/client";

const CATEGORIES = ["dining", "groceries", "transport", "shopping", "entertainment", "subscriptions", "health", "travel", "utilities", "other"];

export function CategoryRules() {
  const [rules, setRules] = useState<CategoryRule[]>([]);
  const [merchant, setMerchant] = useState("");
  const [category, setCategory] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    getCategoryRules().then((data) => { if (active) setRules(data); }).catch(() => { if (active) setMessage("Could not load category rules."); });
    return () => { active = false; };
  }, []);

  async function addRule(event: React.FormEvent) {
    event.preventDefault();
    if (!merchant.trim() || !category || busy) return;
    setBusy(true); setMessage("");
    try {
      const saved = await saveCategoryRule(merchant, category);
      setRules((current) => [...current.filter((rule) => rule.id !== saved.id), saved].sort((a, b) => a.merchant.localeCompare(b.merchant)));
      setMerchant(""); setCategory("");
      setMessage("Rule saved. It will apply during future enrichment or re-categorization.");
    } catch { setMessage("Could not save the rule. Please try again."); }
    finally { setBusy(false); }
  }

  async function toggleRule(rule: CategoryRule) {
    setBusy(true); setMessage("");
    try {
      const updated = await setCategoryRuleEnabled(rule.id, !rule.enabled);
      setRules((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch { setMessage("Could not update the rule. Please try again."); }
    finally { setBusy(false); }
  }

  return <section style={{ background: "#fff", borderRadius: 10, padding: 24, boxShadow: "0 1px 4px rgba(0,0,0,.07)", marginBottom: 24 }}>
    <h2 style={{ fontSize: 16, marginTop: 0 }}>Merchant category rules</h2>
    <p style={{ color: "#687973", fontSize: 13 }}>Match an exact merchant name, ignoring capitalization and extra spaces. Rules apply during future AI processing; manually set categories always take priority. Existing transactions do not change when a rule is saved.</p>
    <form onSubmit={(event) => void addRule(event)} style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "end" }}>
      <label style={{ display: "grid", gap: 5, fontSize: 12 }}>Merchant name<input value={merchant} onChange={(event) => setMerchant(event.target.value)} maxLength={200} placeholder="e.g. Trader Joe's" /></label>
      <label style={{ display: "grid", gap: 5, fontSize: 12 }}>Category<select value={category} onChange={(event) => setCategory(event.target.value)}><option value="">Choose category</option>{CATEGORIES.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
      <button className="settings-button settings-button-primary" type="submit" disabled={busy || !merchant.trim() || !category}>Save rule</button>
    </form>
    {message && <p role="status" style={{ fontSize: 13, color: "#315f49" }}>{message}</p>}
    {rules.length > 0 && <ul style={{ listStyle: "none", padding: 0, margin: "18px 0 0", display: "grid", gap: 8 }}>{rules.map((rule) => <li key={rule.id} style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10, padding: "9px 12px", background: "#f6f9f5", borderRadius: 8, fontSize: 13 }}>
      <span style={{ flex: 1 }}><strong>{rule.merchant}</strong> → {rule.category}{!rule.enabled && " · Paused"}</span>
      <button className="settings-button settings-button-secondary" type="button" disabled={busy} onClick={() => void toggleRule(rule)} aria-label={`${rule.enabled ? "Pause" : "Enable"} rule for ${rule.merchant}`}>{rule.enabled ? "Pause" : "Enable"}</button>
    </li>)}</ul>}
  </section>;
}
