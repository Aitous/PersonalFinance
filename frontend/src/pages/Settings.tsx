import { useEffect, useState } from "react";
import { saveLLMConfig, getLLMConfig, getAccountUsage, exportAccountData, deleteAccount, revokeAIConsent } from "../api/client";
import { useAuth } from "../auth";
import { Link } from "react-router-dom";
import { CategoryRules } from "../components/CategoryRules";
import { ImportWorkspace } from "../components/ImportWorkspace";
import { PlaidConnections } from "../components/PlaidConnections";
import { hostedMode } from "../auth";

const INPUT = { padding: "8px 12px", borderRadius: 6, border: "1px solid #ddd", fontSize: 14, width: "100%", boxSizing: "border-box" as const };
const SECTION = { background: "#fff", borderRadius: 10, padding: 24, boxShadow: "0 1px 4px rgba(0,0,0,0.07)", marginBottom: 24 };

export function Settings() {
  const [llmProvider, setLlmProvider] = useState("claude");
  const [llmKey, setLlmKey] = useState("");
  const [savedMsg, setSavedMsg] = useState("");
  const [usage, setUsage] = useState<{ ai_requests_used: number; ai_requests_limit: number; resets_at: string } | null>(null);
  const [accountError, setAccountError] = useState("");
  const { signOut } = useAuth();

  useEffect(() => {
    getLLMConfig().then((c) => setLlmProvider(c.provider));
    if (hostedMode) getAccountUsage().then(setUsage).catch(() => setAccountError("Could not load account usage."));
  }, []);

  const handleExport = async () => {
    const data = await exportAccountData();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "personal-finance-export.json";
    link.click();
    URL.revokeObjectURL(link.href);
  };

  const handleDelete = async () => {
    if (!window.confirm("Permanently delete your account and imported finance data? This cannot be undone. Disconnect bank accounts first.")) return;
    try { await deleteAccount(); await signOut(); }
    catch { setAccountError("Account deletion could not finish. Disconnect bank accounts first, then try again."); }
  };

  const handleRevokeAI = async () => {
    await revokeAIConsent();
    await signOut();
  };

  const handleLLMSave = async () => {
    await saveLLMConfig(llmProvider, llmKey);
    setLlmKey("");
    setSavedMsg("LLM settings saved.");
    setTimeout(() => setSavedMsg(""), 3000);
  };

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 24 }}>Settings & data</h1>
      <nav className="settings-jumps" aria-label="Settings sections">
        <a href="#ai-provider">AI provider</a><a href="#category-rules">Merchant rules</a><a href="#plaid-sandbox">Bank connections</a><a href="#data-coverage">Imports & data</a>
      </nav>
      {savedMsg && <div style={{ background: "#d1fae5", color: "#065f46", padding: "10px 16px", borderRadius: 8, marginBottom: 20, fontSize: 14 }}>{savedMsg}</div>}

      {!hostedMode && <div id="ai-provider" style={SECTION}>
        <h2 style={{ fontSize: 16, marginTop: 0, marginBottom: 16 }}>AI Provider</h2>
        <div style={{ display: "flex", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
          <select value={llmProvider} onChange={(e) => setLlmProvider(e.target.value)}
            style={{ ...INPUT, maxWidth: 200 }}>
            <option value="claude">Claude (Anthropic)</option>
            <option value="gemini">Gemini (Google)</option>
            <option value="openai">OpenAI (GPT-6 Luna)</option>
          </select>
          <input placeholder={llmProvider === "claude" ? "sk-ant-..." : llmProvider === "gemini" ? "AIza..." : "sk-..."} type="password"
            value={llmKey} onChange={(e) => setLlmKey(e.target.value)}
            style={{ ...INPUT, maxWidth: 280 }} />
          <button onClick={handleLLMSave} disabled={!llmKey.trim()} style={{ background: "#287c61", color: "#fff", border: "none", borderRadius: 6, padding: "8px 16px", cursor: llmKey.trim() ? "pointer" : "not-allowed", fontSize: 14, opacity: llmKey.trim() ? 1 : 0.6 }}>
            Save
          </button>
        </div>
        <p style={{ color: "#888", fontSize: 13 }}>API keys are saved to macOS Keychain.</p>
      </div>}
      {hostedMode && <div id="ai-provider" style={SECTION}>
        <h2 style={{ fontSize: 16, marginTop: 0, marginBottom: 8 }}>AI access</h2>
        <p style={{ color: "#687973", fontSize: 13, margin: 0 }}>AI is provided by this service. Your transactions are sent to the configured model only when you use an AI feature. The monthly request allowance is enforced automatically.</p>
        {usage && <p style={{ color: "#687973", fontSize: 13 }}>Requests this month: <strong>{usage.ai_requests_used} / {usage.ai_requests_limit}</strong>. Resets {new Date(usage.resets_at).toLocaleDateString()}.</p>}
        <button onClick={() => void handleRevokeAI()} style={{ padding: "8px 12px" }}>Turn off AI for my account</button>
      </div>}
      <div id="category-rules"><CategoryRules /></div>
      <PlaidConnections />
      <div id="data-coverage"><ImportWorkspace /></div>
      {hostedMode && <section style={SECTION}>
        <h2 style={{ fontSize: 16, marginTop: 0 }}>Your account data</h2>
        <p style={{ color: "#687973", fontSize: 13 }}>Download a copy of your imported financial data, or permanently close your account.</p>
        {accountError && <p role="alert" style={{ color: "#b42318" }}>{accountError}</p>}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button onClick={() => void handleExport()} style={{ padding: "9px 14px" }}>Export my data</button>
          <button onClick={() => void handleDelete()} style={{ padding: "9px 14px", color: "#b42318" }}>Delete account and data</button>
        </div>
      </section>}
      <div style={SECTION}>
        <h2 style={{ fontSize: 16, marginTop: 0 }}>Overview</h2>
        <p style={{ color: "#687973", fontSize: 13 }}>Return to your monthly spending snapshot and bank sync controls.</p>
        <Link to="/" style={{ color: "#276c54", fontWeight: 700 }}>Open overview →</Link>
      </div>
    </div>
  );
}
