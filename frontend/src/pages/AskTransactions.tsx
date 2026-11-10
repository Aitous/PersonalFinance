import { useState } from "react";
import type { FormEvent } from "react";
import { askTransactions } from "../api/client";
import type { TransactionQuestionContext, TransactionQuestionResult, TransactionQuestionToolEvidence, TransactionQuestionRow } from "../api/client";
import { getAskComparisonView } from "../api/askComparison";
import { DataCoverageNotice } from "../components/DataCoverageNotice";
import "./AskTransactions.css";

const SUGGESTIONS = [
  "What did I spend in Oakland?",
  "Show all Anthropic charges",
  "How much did I spend on groceries last month?",
  "Which transactions were over $100?",
];

const FILTER_LABELS: Record<string, string> = {
  merchant: "Merchant", city: "City", category: "Category", source: "Account",
  date_from: "From", date_to: "Through", amount_min: "Minimum", amount_max: "Maximum",
  transaction_type: "Activity",
};

function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}

function formatFilterValue(key: string, value: string | number) {
  if (key === "amount_min" || key === "amount_max") return formatCurrency(Number(value));
  if (key === "transaction_type") return value === "spending" ? "Purchases" : value === "refunds" ? "Refunds" : String(value);
  return String(value);
}

function getErrorMessage(error: unknown) {
  const failure = error as {
    response?: { status?: number; data?: { detail?: unknown } };
    code?: string;
    message?: string;
  };
  const detail = failure?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (failure?.response?.status === 422) return "Try asking about a merchant, city, category, date range, amount, or account.";
  if (failure?.response?.status && failure.response.status >= 500) {
    return "The transaction search or AI provider had a problem. Your question is still here; try again in a moment.";
  }
  if (failure?.code === "ECONNABORTED") return "This search took too long. Your question is still here; try again.";
  if (!failure?.response) return "Could not reach the transaction service. Check your connection and try again.";
  return failure?.message || "Couldn’t complete that search. Your question is still here; try again.";
}

function getAppliedFilters(criteria: TransactionQuestionResult["criteria"]) {
  return Object.entries(criteria)
    .filter(([key, value]) => value !== null && value !== "" && !(key === "transaction_type" && value === "all"))
    .map(([key, value]) => ({ key, label: FILTER_LABELS[key] || key, value: formatFilterValue(key, value as string | number) }));
}

function Activity({ label, count, transactions, truncated, displayedCount, open }: {
  label: string; count: number; transactions?: TransactionQuestionRow[]; truncated?: boolean; displayedCount?: number; open?: boolean;
}) {
  const shown = displayedCount ?? transactions?.length ?? 0;
  return <details className="ask-transactions-card" open={open}>
    <summary className="ask-results-heading"><div><div className="ask-card-kicker">{label}</div>
      <h2>{count.toLocaleString()} transaction{count === 1 ? "" : "s"}</h2></div>
      <span>{transactions === undefined ? "Activity unavailable for this answer" : truncated
        ? `Showing ${shown.toLocaleString()} of ${count.toLocaleString()} matches`
        : `${shown.toLocaleString()} shown · Inspect transactions`}</span>
    </summary>
    {truncated && <p className="ask-partial-results" role="status">This is a partial list. Totals include all {count.toLocaleString()} matches; the table shows the {shown.toLocaleString()} most recent.</p>}
    {transactions === undefined ? <p className="ask-empty">Ask the question again to load this group’s transactions.</p> : transactions.length ? <div className="ask-table-wrap"><table className="ask-table">
      <thead><tr><th>Date</th><th>Merchant / description</th><th>City</th><th>Category</th><th>Account</th><th>Type</th><th>Amount</th></tr></thead>
      <tbody>{transactions.map((tx) => <tr key={tx.id}>
        <td>{tx.date}</td><td><strong>{tx.merchant_name || tx.description}</strong>
          {tx.merchant_name && tx.description !== tx.merchant_name && <small>{tx.description}</small>}</td>
        <td>{tx.city || "—"}</td><td>{tx.category || "Uncategorized"}</td><td>{tx.source}</td>
        <td>{tx.kind === "refund" || tx.amount < 0 ? "Refund" : tx.kind === "payment" ? "Payment" : "Purchase"}</td>
        <td className={`ask-amount ${tx.kind === "refund" || tx.amount < 0 ? "is-refund" : ""}`}>
          {tx.amount < 0 ? "−" : ""}{formatCurrency(Math.abs(tx.amount))}
        </td>
      </tr>)}</tbody>
    </table></div> : <p className="ask-empty">No transactions matched this group.</p>}
  </details>;
}

function Metric({ label, value, format }: {
  label: string; value: number; format?: (value: number) => string;
}) {
  return <div className="ask-metric">
    <span>{label}</span>
    <strong>{format ? format(value) : value.toLocaleString()}</strong>
  </div>;
}

const TOOL_LABELS: Record<string, string> = {
  search_transactions: "Searched transactions",
  aggregate_results: "Grouped results",
  compare_results: "Compared result sets",
  coverage_summary: "Checked data coverage",
  sql_query: "Ran a read-only query",
  python_analysis: "Ran a calculation",
};

function EvidenceValue({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "") return <>—</>;
  if (typeof value === "number") return <>{value.toLocaleString()}</>;
  if (typeof value === "string" || typeof value === "boolean") return <>{String(value)}</>;
  return <>{JSON.stringify(value)}</>;
}

function QueryEvidenceTable({ columns, rows, sql, caption }: {
  columns: string[]; rows: Array<Record<string, unknown>>; sql?: string; caption: string;
}) {
  return <>
    {sql && <details className="ask-query-source">
      <summary>Show SQL used</summary>
      <pre><code>{sql}</code></pre>
    </details>}
    {columns.length && rows.length ? <div className="ask-table-wrap"><table className="ask-table ask-evidence-table">
      <caption>{caption}</caption>
      <thead><tr>{columns.map((column) => <th key={column}>{column.replaceAll("_", " ")}</th>)}</tr></thead>
      <tbody>{rows.slice(0, 30).map((row, rowIndex) => <tr key={rowIndex}>
        {columns.map((column) => <td key={column}><EvidenceValue value={row[column]} /></td>)}
      </tr>)}</tbody>
    </table></div> : <p className="ask-empty">The query returned no rows.</p>}
    {rows.length > 30 && <p className="ask-partial-results" role="status">Showing 30 of {rows.length.toLocaleString()} returned rows.</p>}
  </>;
}

function EvidencePanel({ items }: { items: TransactionQuestionToolEvidence[] }) {
  if (!items.length) return null;
  const hasMonthly = items.some(({ tool, result }) => tool === "aggregate_results" && result.group_by === "month");
  return <details className="ask-evidence" open={hasMonthly}>
    <summary>Analysis trail <span>{items.length} step{items.length === 1 ? "" : "s"}</span></summary>
    <div className="ask-evidence-content">
      <ol className="ask-step-list" aria-label="Analysis steps">
        {items.map((item, index) => <li key={`${item.tool}-step-${index}`}>
          <span className="ask-step-number">{index + 1}</span>
          <span>{TOOL_LABELS[item.tool] || item.tool.replaceAll("_", " ")}</span>
        </li>)}
      </ol>
      {items.map((item, index) => {
        const result = item.result;
        if (item.tool === "aggregate_results") {
          const groups = result.groups || [];
          return <section className="ask-evidence-block" key={`${item.tool}-${index}`}>
            <h3>{result.group_by === "month" ? "Monthly breakdown" : `Breakdown by ${result.group_by || "group"}`}</h3>
            {result.truncated && <p className="ask-partial-results" role="status">
              This aggregation returned a partial group list. The table shows up to 60 groups; headline totals above cover all matching transactions.
            </p>}
            {groups.length > 0 ? <div className="ask-table-wrap"><table className="ask-table ask-evidence-table">
              <caption>{result.group_by === "month" ? "Monthly gross purchases, refunds, and net spending" : `Totals grouped by ${result.group_by || "group"}`}</caption>
              <thead><tr><th>{result.group_by === "month" ? "Month" : result.group_by || "Group"}</th><th>Transactions</th><th>Gross purchases</th><th>Refunds</th><th>Net spending</th></tr></thead>
              <tbody>{groups.map((group) => <tr key={group.name}>
                <th scope="row">{group.name}</th>
                <td>{group.matching_transaction_count.toLocaleString()}</td>
                <td>{formatCurrency(group.gross_purchases)}</td>
                <td>{formatCurrency(group.refunds)}</td>
                <td>{formatCurrency(group.net_spending)}</td>
              </tr>)}</tbody>
            </table></div> : <p className="ask-empty">No grouped transactions were returned.</p>}
          </section>;
        }
        if (item.tool === "sql_query") {
          const columns = result.columns || [];
          const rows = result.rows || [];
          return <section className="ask-evidence-block" key={`${item.tool}-${index}`}>
            <h3>Query results <span className="ask-evidence-count">{(result.row_count ?? rows.length).toLocaleString()} rows</span></h3>
            <QueryEvidenceTable columns={columns} rows={rows} sql={result.evidence?.sql}
              caption="Read-only results from the transaction data" />
            {(result.truncated || rows.length > 30) && <p className="ask-partial-results" role="status">
              {result.truncated
                ? `Results are limited; showing the first 30 rows of the ${result.row_count?.toLocaleString() ?? "returned"}-row sample.`
                : `Showing 30 of ${result.row_count?.toLocaleString() ?? rows.length.toLocaleString()} returned rows.`}
            </p>}
          </section>;
        }
        if (item.tool === "python_analysis" || item.tool === "python") {
          return <section className="ask-evidence-block" key={`${item.tool}-${index}`}>
            <h3>Calculation details</h3>
            {(result.evidence?.python || result.evidence?.code) && <details className="ask-query-source">
              <summary>Show calculation</summary>
              <pre><code>{result.evidence.python || result.evidence.code}</code></pre>
            </details>}
            {result.evidence?.output && <pre className="ask-code-output">{result.evidence.output}</pre>}
          </section>;
        }
        if (item.tool === "search_transactions") {
          const facts = result.facts;
          const criteria = result.criteria ? getAppliedFilters(result.criteria) : [];
          return <section className="ask-evidence-block ask-search-evidence" key={`${item.tool}-${index}`}>
            <h3>Transaction search <span className="ask-evidence-count">{result.dataset_id || ""}</span></h3>
            {criteria.length > 0 && <div className="ask-applied-filters">
              {criteria.map((filter) => <span className="ask-filter-chip" key={filter.key}><b>{filter.label}</b> {filter.value}</span>)}
            </div>}
            {facts && <div className="ask-metrics">
              <Metric label="Matches" value={facts.matching_transaction_count} />
              <Metric label="Gross purchases" value={facts.gross_purchases} format={formatCurrency} />
              <Metric label="Refunds" value={facts.refunds} format={formatCurrency} />
              <Metric label="Net spending" value={facts.net_spending} format={formatCurrency} />
            </div>}
          </section>;
        }
        if (item.tool === "compare_results") {
          return <section className="ask-evidence-block" key={`${item.tool}-${index}`}>
            <h3>Comparison evidence</h3>
            {result.left_facts && <p>First set: {result.left_facts.matching_transaction_count.toLocaleString()} matches · {formatCurrency(result.left_facts.net_spending)} net spending</p>}
            {result.right_facts && <p>Second set: {result.right_facts.matching_transaction_count.toLocaleString()} matches · {formatCurrency(result.right_facts.net_spending)} net spending</p>}
          </section>;
        }
        return <section className="ask-evidence-block ask-city-coverage" key={`${item.tool}-${index}`}>
          <h3>City data coverage</h3>
          <p>{result.transactions_missing_city_in_scope?.toLocaleString() ?? "Unknown"} {result.scope_dataset_id ? "matching " : "imported "}transaction{result.transactions_missing_city_in_scope === 1 ? " has" : "s have"} no city recorded.</p>
          <p>{result.transactions_missing_city_in_full_dataset?.toLocaleString() ?? "Unknown"} transaction{result.transactions_missing_city_in_full_dataset === 1 ? " has" : "s have"} no city across all imported data.</p>
          {(result.observed_from || result.observed_through) && <p>Observed dates: {result.observed_from || "unknown start"} – {result.observed_through || "unknown end"}.</p>}
          {result.note && <small>{result.note}</small>}
        </section>;
      })}
    </div>
  </details>;
}

export function AskTransactions() {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Array<{ id: number; question: string; result: TransactionQuestionResult }>>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!question.trim() || loading) return;
    setLoading(true);
    setError("");
    try {
      const history: TransactionQuestionContext[] = turns.slice(-5).map((turn) => ({
        question: turn.question,
        answer: turn.result.answer,
        criteria: turn.result.criteria,
        match_count: turn.result.match_count,
        gross_purchases: turn.result.gross_purchases,
        refunds: turn.result.refunds,
      }));
      const asked = question.trim();
      const result = await askTransactions(asked, history);
      setTurns((current) => [...current, { id: Date.now(), question: asked, result }]);
      setQuestion("");
    } catch (failure) {
      setError(getErrorMessage(failure));
    } finally {
      setLoading(false);
    }
  };

  return <div className="ask-page">
    <header className="ask-header">
      <div><span className="section-kicker">TRANSACTION EXPLORER</span><h1>Ask your transactions</h1>
        <p>Ask follow-up questions about merchants, places, categories, dates, or amounts.</p>
      </div>
      {turns.length > 0 && <button className="ask-new-chat" type="button" onClick={() => { setTurns([]); setError(""); }}>
        New conversation
      </button>}
    </header>
    <DataCoverageNotice locationGuidance />

    {turns.length > 0 && <section className="ask-chat" aria-label="Conversation" aria-live="polite">
      {turns.map((turn, index) => {
        const sqlOnly = turn.result.analysis_mode === "sql";
        const filters = getAppliedFilters(turn.result.criteria);
        const displayedCount = turn.result.displayed_count ?? turn.result.transactions.length;
        return <article className="ask-turn" key={turn.id}>
          <div className="ask-user-message"><span>You</span><p>{turn.question}</p></div>
          <div className="ask-answer-card">
            <div className="ask-card-kicker">{sqlOnly ? "ANSWER · QUERY ANALYSIS" : "ANSWER"}</div>
            <p>{turn.result.answer}</p>
            {!sqlOnly && <div className="ask-applied-filters" aria-label="Applied filters">
              <span className="ask-filter-label">APPLIED FILTERS</span>
              {filters.length ? filters.map((filter) => <span className="ask-filter-chip" key={filter.key}>
                <b>{filter.label}</b> {filter.value}
              </span>) : <span className="ask-filter-chip">No filters reported</span>}
            </div>}
            {!sqlOnly && <div className="ask-metrics">
              <Metric label="Matching transactions" value={turn.result.match_count} />
              <Metric label="Gross purchases" value={turn.result.gross_purchases} format={formatCurrency} />
              <Metric label="Refunds" value={turn.result.refunds} format={formatCurrency} />
            </div>}
            {turn.result.comparison && (() => {
              const comparison = getAskComparisonView(turn.result.comparison);
              if (comparison.kind === "sql") return <section className="ask-sql-comparison" aria-label="SQL comparison evidence">
                <h2>Comparison evidence</h2>
                <p>These are grouped query results; individual transactions are not included in this comparison. Ask to list the transactions for either group to see them.</p>
                <QueryEvidenceTable columns={comparison.columns} rows={comparison.rows} sql={comparison.sql}
                  caption="Read-only results used for this comparison" />
              </section>;
              return <div className="ask-comparison" aria-label="Requested comparison">
                <div className="ask-comparison-heading"><strong>Compared with</strong></div>
                <div className="ask-applied-filters" aria-label="Comparison filters">
                  {getAppliedFilters(comparison.criteria).map((filter) => <span className="ask-filter-chip" key={filter.key}>
                    <b>{filter.label}</b> {filter.value}
                  </span>)}
                </div>
                <Metric label="Matching transactions" value={comparison.match_count} />
                <Metric label="Gross purchases" value={comparison.gross_purchases} format={formatCurrency} />
                <Metric label="Refunds" value={comparison.refunds} format={formatCurrency} />
                <Metric label="Net spending" value={comparison.net_spending} format={formatCurrency} />
                {comparison.left && <Metric label="Other group net spending" value={comparison.left.net_spending} format={formatCurrency} />}
                {comparison.net_spending_delta_right_minus_left !== undefined && <Metric
                  label="Net spending difference" value={comparison.net_spending_delta_right_minus_left} format={formatCurrency} />}
              </div>;
            })()}
            {turn.result.tool_results && <EvidencePanel items={turn.result.tool_results} />}
            {turn.result.coverage?.note && <div className="ask-result-coverage" role="note">
              <strong>Coverage for this answer</strong>
              <span>{turn.result.coverage.note}</span>
              {(turn.result.coverage.observed_from || turn.result.coverage.observed_through) && <small>
                Observed activity: {turn.result.coverage.observed_from || "unknown start"} – {turn.result.coverage.observed_through || "unknown end"}
              </small>}
            </div>}
          </div>
          {!sqlOnly && <Activity label={turn.result.comparison && turn.result.comparison.source !== "sql" ? `MATCHING ACTIVITY · ${filters.map((f) => f.value).join(" · ") || "FIRST GROUP"}` : "MATCHING ACTIVITY"}
            count={turn.result.match_count} transactions={turn.result.transactions} truncated={turn.result.truncated} displayedCount={displayedCount} open={index === turns.length - 1} />}
          {!sqlOnly && turn.result.comparison && turn.result.comparison.source !== "sql" && <Activity
            label={`COMPARISON ACTIVITY · ${getAppliedFilters(turn.result.comparison.criteria).map((f) => f.value).join(" · ") || "SECOND GROUP"}`}
            count={turn.result.comparison.match_count} transactions={turn.result.comparison.transactions}
            truncated={turn.result.comparison.truncated} displayedCount={turn.result.comparison.displayed_count} open={index === turns.length - 1} />}
        </article>;
      })}
    </section>}

    {error && <div className="ask-error" role="alert"><span>{error}</span>
      <button type="button" onClick={() => setError("")}>Dismiss</button>
    </div>}
    {loading && <p className="ask-loading" role="status">Finding matching transactions and preparing an answer…</p>}

    {turns.length === 0 && <div className="ask-first-question">Try asking about a merchant, a city, or a spending category.</div>}
    <form className="ask-form" onSubmit={submit}>
      <label htmlFor="transaction-question">{turns.length ? "Ask a follow-up" : "What would you like to know?"}</label>
      <div className="ask-input-row">
        <input id="transaction-question" value={question} onChange={(event) => setQuestion(event.target.value)}
          placeholder={turns.length ? "e.g. How much of that was in Oakland?" : "e.g. What are all the transactions in Oakland?"} maxLength={1000} />
        <button type="submit" disabled={loading || !question.trim()}>{loading ? "Searching…" : error ? "Try again" : "Ask"}</button>
      </div>
      {turns.length === 0 && <div className="ask-suggestions" aria-label="Suggested questions">
        {SUGGESTIONS.map((suggestion) => <button type="button" key={suggestion}
          onClick={() => { setQuestion(suggestion); setError(""); }}>{suggestion}</button>)}
      </div>}
    </form>
  </div>;
}
