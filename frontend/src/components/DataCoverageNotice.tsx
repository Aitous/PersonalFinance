import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getDataQuality } from "../api/client";
import type { DataQuality } from "../api/client";

export function DataCoverageNotice() {
  const [quality, setQuality] = useState<DataQuality | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    getDataQuality()
      .then((value) => { if (active) { setQuality(value); setError(false); } })
      .catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [attempt]);

  if (error) return <div className="data-coverage-notice" role="status">
    Data coverage details are unavailable. <button type="button" onClick={() => setAttempt((v) => v + 1)}>Retry</button>
  </div>;
  if (!quality) return <div className="data-coverage-notice" role="status">Loading data coverage…</div>;

  return <aside className="data-coverage-notice" aria-label="Data coverage context">
    <div className="data-coverage-heading">
      <strong>Based on {quality.total_transactions.toLocaleString()} imported transactions</strong>
      <Link to="/settings#data-coverage">Review imports</Link>
    </div>
    <div className="data-coverage-sources">
      {quality.sources.map((source) => <span key={source.source}>
        <strong>{source.source}</strong> · {source.transaction_count} rows · observed {source.first_date ?? "—"} to {source.last_date ?? "—"}
      </span>)}
    </div>
    <div className="data-coverage-gaps">
      {quality.missing_merchant} unknown merchants · {quality.missing_city} unknown cities · {quality.missing_category} uncategorized · {quality.enrichment_fallback} enrichment fallbacks · {quality.unassigned_account} without an account
    </div>
    <p>{quality.coverage_note}</p>
  </aside>;
}
