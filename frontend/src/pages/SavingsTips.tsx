import { useEffect, useState } from "react";
import { getSavingsTips, getLLMConfig } from "../api/client";

export function SavingsTips() {
  const [tips, setTips] = useState<string[]>([]);
  const [period, setPeriod] = useState("");
  const [loading, setLoading] = useState(false);
  const [provider, setProvider] = useState("claude");

  useEffect(() => { getLLMConfig().then((c) => setProvider(c.provider)); }, []);

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const result = await getSavingsTips();
      setTips(result.tips);
      setPeriod(result.period);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 8 }}>Savings Tips</h1>
      <p style={{ color: "#888", marginBottom: 24 }}>AI-generated suggestions based on your last 3 months of spending</p>

      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 24 }}>
        <select value={provider} onChange={(e) => setProvider(e.target.value)}
          style={{ padding: "8px 12px", borderRadius: 6, border: "1px solid #ddd", fontSize: 14 }}>
          <option value="claude">Claude (Anthropic)</option>
          <option value="gemini">Gemini (Google)</option>
        </select>
        <button onClick={handleGenerate} disabled={loading} style={{
          background: "#7c6af7", color: "#fff", border: "none",
          borderRadius: 8, padding: "8px 20px", cursor: "pointer", fontSize: 14,
        }}>
          {loading ? "Generating…" : tips.length ? "Regenerate Tips" : "Generate Tips"}
        </button>
      </div>

      {period && <p style={{ color: "#888", fontSize: 13, marginBottom: 16 }}>Analysis period: {period}</p>}

      {tips.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {tips.map((tip, i) => (
            <div key={i} style={{ background: "#fff", borderRadius: 10, padding: "16px 20px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)", display: "flex", gap: 14 }}>
              <span style={{ fontSize: 20 }}>💡</span>
              <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6 }}>{tip}</p>
            </div>
          ))}
        </div>
      )}

      {tips.length === 0 && !loading && (
        <p style={{ color: "#aaa", textAlign: "center", marginTop: 60 }}>Click "Generate Tips" to get personalized saving suggestions.</p>
      )}
    </div>
  );
}
