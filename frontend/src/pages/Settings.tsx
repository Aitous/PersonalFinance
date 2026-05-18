import { useEffect, useState } from "react";
import { saveBankCredentials, getConfiguredBanks, saveLLMConfig, getLLMConfig } from "../api/client";

const BANKS = [
  { id: "chase", label: "Chase" },
  { id: "discover", label: "Discover" },
  { id: "amex", label: "American Express" },
];

const INPUT = { padding: "8px 12px", borderRadius: 6, border: "1px solid #ddd", fontSize: 14, width: "100%", boxSizing: "border-box" as const };
const SECTION = { background: "#fff", borderRadius: 10, padding: 24, boxShadow: "0 1px 4px rgba(0,0,0,0.07)", marginBottom: 24 };

export function Settings() {
  const [configuredBanks, setConfiguredBanks] = useState<Record<string, boolean>>({});
  const [bankForms, setBankForms] = useState<Record<string, { username: string; password: string }>>({});
  const [llmProvider, setLlmProvider] = useState("claude");
  const [llmKey, setLlmKey] = useState("");
  const [savedMsg, setSavedMsg] = useState("");

  useEffect(() => {
    getConfiguredBanks().then(setConfiguredBanks);
    getLLMConfig().then((c) => setLlmProvider(c.provider));
  }, []);

  const handleBankSave = async (bank: string) => {
    const { username, password } = bankForms[bank] ?? {};
    if (!username || !password) return;
    await saveBankCredentials(bank, username, password);
    setConfiguredBanks((prev) => ({ ...prev, [bank]: true }));
    setBankForms((prev) => ({ ...prev, [bank]: { username: "", password: "" } }));
    setSavedMsg(`${bank} credentials saved.`);
    setTimeout(() => setSavedMsg(""), 3000);
  };

  const handleLLMSave = async () => {
    await saveLLMConfig(llmProvider, llmKey);
    setLlmKey("");
    setSavedMsg("LLM settings saved.");
    setTimeout(() => setSavedMsg(""), 3000);
  };

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 24 }}>Settings</h1>
      {savedMsg && <div style={{ background: "#d1fae5", color: "#065f46", padding: "10px 16px", borderRadius: 8, marginBottom: 20, fontSize: 14 }}>{savedMsg}</div>}

      <div style={SECTION}>
        <h2 style={{ fontSize: 16, marginTop: 0, marginBottom: 20 }}>Bank Credentials</h2>
        <p style={{ color: "#888", fontSize: 13, marginBottom: 20 }}>Credentials are saved to macOS Keychain — never written to disk.</p>
        {BANKS.map(({ id, label }) => (
          <div key={id} style={{ marginBottom: 24 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
              <span style={{ fontSize: 15, fontWeight: 600 }}>{label}</span>
              {configuredBanks[id] && <span style={{ background: "#d1fae5", color: "#065f46", fontSize: 11, padding: "2px 8px", borderRadius: 10 }}>Configured</span>}
            </div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <input placeholder="Username" value={bankForms[id]?.username ?? ""} type="text"
                onChange={(e) => setBankForms((p) => ({ ...p, [id]: { ...p[id], username: e.target.value } }))}
                style={{ ...INPUT, maxWidth: 200 }} />
              <input placeholder="Password" value={bankForms[id]?.password ?? ""} type="password"
                onChange={(e) => setBankForms((p) => ({ ...p, [id]: { ...p[id], password: e.target.value } }))}
                style={{ ...INPUT, maxWidth: 200 }} />
              <button onClick={() => handleBankSave(id)} style={{ background: "#7c6af7", color: "#fff", border: "none", borderRadius: 6, padding: "8px 16px", cursor: "pointer", fontSize: 14 }}>
                Save
              </button>
            </div>
          </div>
        ))}
      </div>

      <div style={SECTION}>
        <h2 style={{ fontSize: 16, marginTop: 0, marginBottom: 16 }}>AI Provider</h2>
        <div style={{ display: "flex", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
          <select value={llmProvider} onChange={(e) => setLlmProvider(e.target.value)}
            style={{ ...INPUT, maxWidth: 200 }}>
            <option value="claude">Claude (Anthropic)</option>
            <option value="gemini">Gemini (Google)</option>
          </select>
          <input placeholder={llmProvider === "claude" ? "sk-ant-..." : "AIza..."} type="password"
            value={llmKey} onChange={(e) => setLlmKey(e.target.value)}
            style={{ ...INPUT, maxWidth: 280 }} />
          <button onClick={handleLLMSave} style={{ background: "#7c6af7", color: "#fff", border: "none", borderRadius: 6, padding: "8px 16px", cursor: "pointer", fontSize: 14 }}>
            Save
          </button>
        </div>
        <p style={{ color: "#888", fontSize: 13 }}>API keys are saved to macOS Keychain.</p>
      </div>
    </div>
  );
}
