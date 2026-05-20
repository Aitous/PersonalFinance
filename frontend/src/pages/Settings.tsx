import { useEffect, useState } from "react";
import { saveLLMConfig, getLLMConfig } from "../api/client";

const INPUT = { padding: "8px 12px", borderRadius: 6, border: "1px solid #ddd", fontSize: 14, width: "100%", boxSizing: "border-box" as const };
const SECTION = { background: "#fff", borderRadius: 10, padding: 24, boxShadow: "0 1px 4px rgba(0,0,0,0.07)", marginBottom: 24 };

export function Settings() {
  const [llmProvider, setLlmProvider] = useState("claude");
  const [llmKey, setLlmKey] = useState("");
  const [savedMsg, setSavedMsg] = useState("");

  useEffect(() => {
    getLLMConfig().then((c) => setLlmProvider(c.provider));
  }, []);

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
