import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, Cell, LabelList, ResponsiveContainer,
} from "recharts";
import { getTransactions } from "../api/client";
import { getMonthlyReport, generateNarrative, getCachedCategoryExplanations, generateCategoryExplanations } from "../api/reports";
import type { MonthlyReport, MonthlyCategoryExplanations } from "../api/reports";
import { reportPeriodRange } from "../api/reliabilityHelpers";
import { monthlyReportTotals } from "../api/reportTotals";
import { DataCoverageNotice } from "../components/DataCoverageNotice";

interface StatCard {
  label: string;
  value: string;
  valueColor?: string;
  sub?: string;
}

interface ReportDrilldown {
  category?: string;
  merchant?: string;
  label: string;
  date_from: string;
  date_to: string;
}

interface ReportTransaction {
  id: string;
  date: string;
  description: string;
  amount: number;
  source: string;
  merchant_name?: string | null;
}

function lastCompleteMonth(): { year: number; month: number } {
  const today = new Date();
  const month = today.getMonth(); // 0-indexed, so this is "previous month" in 1-indexed
  const year = month === 0 ? today.getFullYear() - 1 : today.getFullYear();
  return { year, month: month === 0 ? 12 : month };
}

const MONTH_NAMES = [
  "", "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function pctChange(current: number, prior: number): string | null {
  if (prior === 0) return null;
  const pct = ((current - prior) / prior) * 100;
  return (pct > 0 ? "+" : "") + pct.toFixed(1) + "%";
}

function fmt(n: number): string {
  return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

export default function Reports() {
  const navigate = useNavigate();
  const initial = lastCompleteMonth();
  const [year, setYear] = useState(initial.year);
  const [month, setMonth] = useState(initial.month);
  const [report, setReport] = useState<MonthlyReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [narrativeLoading, setNarrativeLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [drilldown, setDrilldown] = useState<ReportDrilldown | null>(null);
  const [drilldownTransactions, setDrilldownTransactions] = useState<ReportTransaction[]>([]);
  const [drilldownLoading, setDrilldownLoading] = useState(false);
  const [drilldownError, setDrilldownError] = useState<string | null>(null);
  const [categoryComparison, setCategoryComparison] = useState<"recent3" | "prior">("recent3");
  const [categoryExplanationResult, setCategoryExplanationResult] = useState<MonthlyCategoryExplanations | null>(null);
  const [categoryExplanationLoading, setCategoryExplanationLoading] = useState(false);
  const [categoryExplanationChecking, setCategoryExplanationChecking] = useState(true);
  const [categoryExplanationError, setCategoryExplanationError] = useState<string | null>(null);
  const categoryExplanationRequestKey = `${year}-${month}-${categoryComparison}`;
  const categoryExplanationRequestKeyRef = useRef(categoryExplanationRequestKey);
  categoryExplanationRequestKeyRef.current = categoryExplanationRequestKey;
  const closeDrilldownButton = useRef<HTMLButtonElement>(null);
  const drilldownTrigger = useRef<HTMLElement | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setReport(null);
    getMonthlyReport(year, month)
      .then((result) => { if (active) setReport(result); })
      .catch(() => { if (active) setError("Failed to load report."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [year, month, reloadToken]);

  useEffect(() => {
    setCategoryExplanationLoading(false);
    if (!report || report.year !== year || report.month !== month || loading) return;
    let active = true;
    setCategoryExplanationResult(null);
    setCategoryExplanationError(null);
    setCategoryExplanationChecking(true);
    if (categoryComparison === "recent3" && !report.recent_three_months_all_observed) {
      setCategoryExplanationChecking(false);
      return () => { active = false; };
    }
    getCachedCategoryExplanations(year, month, categoryComparison)
      .then((result) => {
        if (!active) return;
        if (result.explanations) {
          setCategoryExplanationResult(result);
          return;
        }
      })
      .catch(() => { if (active) setCategoryExplanationError("Could not check for saved explanations."); })
      .finally(() => { if (active) setCategoryExplanationChecking(false); });
    return () => { active = false; };
  }, [year, month, categoryComparison, report, loading]);

  useEffect(() => {
    if (!drilldown) return;
    let active = true;
    setDrilldownTransactions([]);
    setDrilldownLoading(true);
    setDrilldownError(null);
    getTransactions({
      category: drilldown.category,
      merchant: drilldown.merchant,
      date_from: drilldown.date_from,
      date_to: drilldown.date_to,
      tx_type: "spending",
    })
      .then((rows: ReportTransaction[]) => { if (active) setDrilldownTransactions(rows); })
      .catch(() => { if (active) setDrilldownError("Could not load these transactions. Please close this panel and try again."); })
      .finally(() => { if (active) setDrilldownLoading(false); });
    return () => { active = false; };
  }, [drilldown]);

  useEffect(() => {
    if (!drilldown) {
      drilldownTrigger.current?.focus();
      return;
    }
    closeDrilldownButton.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrilldown(null);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [drilldown]);

  function stepMonth(delta: number) {
    let m = month + delta;
    let y = year;
    if (m < 1) { m = 12; y -= 1; }
    if (m > 12) { m = 1; y += 1; }
    setYear(y);
    setMonth(m);
  }

  async function handleGenerateNarrative() {
    if (!report) return;
    setNarrativeLoading(true);
    try {
      const narrative = await generateNarrative(year, month);
      setReport({ ...report, narrative });
    } catch {
      setError("Failed to generate summary.");
    } finally {
      setNarrativeLoading(false);
    }
  }

  async function handleGenerateCategoryExplanations() {
    const requestKey = categoryExplanationRequestKey;
    setCategoryExplanationLoading(true);
    setCategoryExplanationError(null);
    try {
      const result = await generateCategoryExplanations(year, month, categoryComparison);
      if (categoryExplanationRequestKeyRef.current === requestKey) setCategoryExplanationResult(result);
    } catch {
      if (categoryExplanationRequestKeyRef.current === requestKey) {
        setCategoryExplanationError("Could not explain the category changes. Check your AI provider settings and try again.");
      }
    } finally {
      if (categoryExplanationRequestKeyRef.current === requestKey) setCategoryExplanationLoading(false);
    }
  }

  function openCategoryPeriod(category: string, series: "current" | "prior") {
    const range = reportPeriodRange(year, month, series);
    if (!range) return;
    drilldownTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const selectedMonth = series === "current" ? month : month === 1 ? 12 : month - 1;
    const selectedYear = series === "current" ? year : month === 1 ? year - 1 : year;
    setDrilldown({
      category,
      label: `${MONTH_NAMES[selectedMonth]} ${selectedYear}`,
      date_from: range.date_from!,
      date_to: range.date_to!,
    });
  }

  function openMerchantPeriod(merchant: string, date_from: string, date_to: string) {
    drilldownTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setDrilldown({ merchant, label: `${MONTH_NAMES[month]} ${year}`, date_from, date_to });
  }

  const priorMonth = month === 1 ? 12 : month - 1;
  const priorYear = month === 1 ? year - 1 : year;
  const totals = report ? monthlyReportTotals(report) : null;
  const drilldownTotal = drilldownTransactions.reduce((sum, transaction) => sum + Math.max(0, transaction.amount), 0);
  const allDataAverageChange = report?.all_data_monthly_average == null
    ? null
    : pctChange(report.total, report.all_data_monthly_average);
  const recentMonthLabels = report?.recent_three_months.map((item) => {
    const [monthYear, monthNumber] = item.month.split("-").map(Number);
    return { label: MONTH_NAMES[monthNumber].slice(0, 3), year: monthYear };
  }) ?? [];
  const recentWindowLabel = recentMonthLabels.length === 3
    ? recentMonthLabels[0].year === recentMonthLabels[2].year
      ? `${recentMonthLabels[0].label}–${recentMonthLabels[2].label} ${recentMonthLabels[2].year}`
      : `${recentMonthLabels[0].label} ${recentMonthLabels[0].year}–${recentMonthLabels[2].label} ${recentMonthLabels[2].year}`
    : "previous 3 calendar months";
  const recentObservedCount = report?.recent_three_months.filter((item) => item.observed_activity).length ?? 0;
  const categoryDeltas = report?.categories
    .map((category) => ({
      name: category.name,
      delta: category.current - (categoryComparison === "recent3"
        ? (category.recent_three_month_average ?? category.current)
        : category.prior),
    }))
    .filter((item) => (categoryComparison === "prior" || report.categories.find((category) => category.name === item.name)?.recent_three_month_average != null) && Math.abs(item.delta) >= 0.01)
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)) ?? [];
  const maxCategoryDelta = Math.max(100, Math.ceil(Math.max(...categoryDeltas.map((item) => Math.abs(item.delta)), 0) / 100) * 100);
  const largestIncrease = categoryDeltas.find((item) => item.delta > 0);
  const largestDecrease = categoryDeltas.filter((item) => item.delta < 0).sort((a, b) => a.delta - b.delta)[0];

  const card: React.CSSProperties = {
    background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12, padding: "20px 24px", marginBottom: 20,
  };
  const label: React.CSSProperties = { fontSize: 12, color: "#9ca3af", marginBottom: 4 };
  const sectionTitle: React.CSSProperties = {
    fontSize: 13, fontWeight: 700, color: "#6d5bd0", letterSpacing: "0.05em",
    textTransform: "uppercase", marginBottom: 14,
  };

  return (
    <div style={{ maxWidth: 1000, margin: "0 auto", padding: "24px 0", color: "#1f2937" }}>
      {/* Header + month picker */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 28 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: "#111827", margin: 0 }}>Monthly Report</h1>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            onClick={() => stepMonth(-1)}
            aria-label="Previous month" style={{ background: "#fff", border: "1px solid #d1d5db", color: "#4b5563", borderRadius: 8, padding: "6px 14px", cursor: "pointer", fontSize: 16 }}
          >◀</button>
          <span style={{ fontWeight: 600, fontSize: 16, minWidth: 140, textAlign: "center" }}>
            {MONTH_NAMES[month]} {year}
          </span>
          <button
            onClick={() => stepMonth(1)}
            aria-label="Next month" style={{ background: "#fff", border: "1px solid #d1d5db", color: "#4b5563", borderRadius: 8, padding: "6px 14px", cursor: "pointer", fontSize: 16 }}
          >▶</button>
        </div>
      </div>

      <p className="monthly-report-comparison-intro">Compare each category with last month and your average across other available months.</p>

      <DataCoverageNotice />

      {loading && <div style={{ color: "#9ca3af", textAlign: "center", padding: 60 }}>Loading...</div>}
      {error && <div role="alert" style={{ color: "#b91c1c", textAlign: "center", padding: 40 }}>{error}<div><button onClick={() => setReloadToken((v) => v + 1)} style={{ marginTop: 10, border: "1px solid #ddd", borderRadius: 6, background: "#fff", padding: "7px 12px", cursor: "pointer" }}>Retry</button></div></div>}

      {report && !loading && (
        <>
          {/* 1. AI Narrative */}
          <div style={card}>
            <div style={sectionTitle}>Summary</div>
            {report.narrative ? (
              <p style={{ margin: 0, lineHeight: 1.7, color: "#374151" }}>{report.narrative}</p>
            ) : (
              <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                <p style={{ margin: 0, color: "#6b7280" }}>No summary generated yet.</p>
                <button
                  onClick={handleGenerateNarrative}
                  disabled={narrativeLoading}
                  style={{
                    background: "#287c61", border: "none", color: "#fff", borderRadius: 8,
                    padding: "8px 18px", cursor: narrativeLoading ? "default" : "pointer",
                    fontSize: 13, opacity: narrativeLoading ? 0.6 : 1,
                  }}
                >
                  {narrativeLoading ? "Generating…" : "Generate summary"}
                </button>
              </div>
            )}
          </div>

          {/* 2. Stats row */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 16, marginBottom: 20 }}>
            {([
              { label: "Gross purchases", value: fmt(totals!.gross) },
              { label: "Refunds", value: fmt(totals!.refunds) },
              { label: "Net spending", value: fmt(totals!.net) },
              {
                label: "Gross purchases vs last month",
                value: pctChange(report.total, report.prev_total) ?? "—",
                valueColor: report.total <= report.prev_total ? "#047857" : "#b91c1c",
                sub: report.prev_total > 0
                  ? `${report.total <= report.prev_total ? "−" : "+"}${fmt(Math.abs(report.total - report.prev_total))}`
                  : undefined,
              },
              {
                label: "Gross purchases vs all-history average (reference)",
                value: allDataAverageChange ?? "—",
                valueColor: report.all_data_monthly_average == null ? "#6b7280" : report.total <= report.all_data_monthly_average ? "#047857" : "#b91c1c",
                sub: report.all_data_monthly_average == null
                  ? "Average unavailable"
                  : `${fmt(report.all_data_monthly_average)}/mo · ${report.average_month_count} months`,
              },
              { label: "Transactions", value: String(report.tx_count) },
            ] as StatCard[]).map((s) => (
              <div key={s.label} style={{ ...card, flex: 1, marginBottom: 0, textAlign: "center" }}>
                <div style={label}>{s.label}</div>
                <div style={{ fontSize: 26, fontWeight: 700, color: s.valueColor ?? "#1f2937" }}>{s.value}</div>
                {s.sub && <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 2 }}>{s.sub}</div>}
              </div>
            ))}
          </div>

          {/* 3. Category breakdown */}
          {report.categories.length > 0 && (
            <div style={card}>
              <div style={sectionTitle}>What changed by category?</div>
              <p className="monthly-report-average-note">
                The main comparison uses the three calendar months immediately before this report. Missing months are not replaced with older ones. All-history average remains a reference and may include later transactions when viewing older reports. Statement coverage may still have gaps.
                {report.recent_three_months_all_observed ? ` Window: ${recentWindowLabel} · activity observed in all 3 months; statement coverage may still be incomplete.` : ` Window: ${recentWindowLabel} · transaction activity observed in ${recentObservedCount} of 3 months, so the recent baseline is unavailable.`}
              </p>
              <div className="monthly-report-chart-controls" role="group" aria-label="Choose category comparison">
                <button type="button" aria-pressed={categoryComparison === "recent3"} onClick={() => setCategoryComparison("recent3")}>Vs previous 3-month average</button>
                <button type="button" aria-pressed={categoryComparison === "prior"} onClick={() => setCategoryComparison("prior")}>Vs prior month</button>
              </div>
              <div className="monthly-report-chart-movers" aria-live="polite">
                {largestIncrease && <span className="is-increase"><strong>Largest increase</strong>{largestIncrease.name} · +{fmt(largestIncrease.delta)}</span>}
                {largestDecrease && <span className="is-decrease"><strong>Largest decrease</strong>{largestDecrease.name} · −{fmt(Math.abs(largestDecrease.delta))}</span>}
              </div>
              <ResponsiveContainer width="100%" height={Math.max(240, categoryDeltas.length * 34 + 38)}>
                <BarChart
                  data={categoryDeltas}
                  layout="vertical"
                  margin={{ left: 8, right: 18, top: 4, bottom: 4 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5ebe6" horizontal={false} />
                  <XAxis type="number" domain={[-maxCategoryDelta, maxCategoryDelta]} tickFormatter={(value) => `${value < 0 ? "−" : ""}${fmt(Math.abs(Number(value)))}`} tick={{ fill: "#87938b", fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" tick={{ fill: "#374151", fontSize: 12 }} width={94} />
                  <Tooltip
                    cursor={{ fill: "#f5f8f5" }}
                    contentStyle={{ background: "#fff", border: "1px solid #cbdccf", borderRadius: 8, boxShadow: "0 6px 18px rgba(23,53,49,.12)" }}
                    labelStyle={{ color: "#173531", fontWeight: 700 }}
                    itemStyle={{ color: "#304b40" }}
                    formatter={(v) => {
                      const value = Number(v ?? 0);
                      return [`${value > 0 ? "+" : value < 0 ? "−" : ""}${fmt(Math.abs(value))}`, categoryComparison === "recent3" ? `Change vs ${recentWindowLabel} average` : "Change vs prior month"];
                    }}
                  />
                  <ReferenceLine x={0} stroke="#66756b" strokeWidth={1.5} />
                  <Bar dataKey="delta" name="Change" radius={[4, 4, 4, 4]}>
                    {categoryDeltas.map((item) => <Cell key={item.name} fill={item.delta > 0 ? "#d7795d" : item.delta < 0 ? "#37836a" : "#9aa69d"} />)}
                    <LabelList dataKey="delta" content={(props: any) => {
                      const { x = 0, y = 0, width = 0, height = 0, value = 0 } = props;
                      const amount = Number(value);
                      const text = `${amount > 0 ? "+" : amount < 0 ? "−" : ""}${fmt(Math.abs(amount))}`;
                      const fitsInside = Math.abs(width) >= 64;
                      return <text
                        x={fitsInside ? x + width / 2 : amount < 0 ? x - 7 : x + width + 7}
                        y={y + height / 2}
                        textAnchor={fitsInside ? "middle" : amount < 0 ? "end" : "start"}
                        dominantBaseline="central"
                        fill={fitsInside ? "#fff" : "#35473d"}
                        fontSize={11}
                        fontWeight={700}
                        pointerEvents="none"
                      >{text}</text>;
                    }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
                <div className="monthly-report-category-table-wrap">
                  <table className="monthly-report-category-table">
                    <thead><tr>
                      <th scope="col">Category</th>
                      <th scope="col">{MONTH_NAMES[month]} {year}</th>
                      <th scope="col">{MONTH_NAMES[priorMonth]} {priorYear}</th>
                      <th scope="col">Recent avg / month<small>{recentWindowLabel} · {recentObservedCount}/3 observed</small></th>
                      <th scope="col">All-history avg / month<small>Reference · {report.average_period_start && report.average_period_end ? `${report.average_period_start} to ${report.average_period_end}` : "period unavailable"}</small></th>
                      <th scope="col" className="monthly-report-explanation-heading">
                        <span>Why it changed</span>
                        <small>{categoryComparison === "recent3" ? `vs ${recentWindowLabel} average` : "vs prior month"}</small>
                        {!categoryExplanationResult && (categoryExplanationLoading || categoryExplanationChecking
                          ? <small role="status">{categoryExplanationLoading ? "Generating explanations…" : "Loading saved explanations…"}</small>
                          : <><button type="button" onClick={handleGenerateCategoryExplanations}>{categoryExplanationError ? "Retry explanations" : "Generate explanations"}</button>{categoryExplanationError && <small role="alert">AI explanation unavailable.</small>}</>)}
                      </th>
                    </tr></thead>
                    <tbody>{report.categories.map((category) => (
                      (() => {
                        const baseline = categoryComparison === "recent3" ? category.recent_three_month_average : category.prior;
                        const delta = baseline == null ? null : category.current - baseline;
                        const explanation = categoryExplanationResult?.explanations?.[category.name];
                        const evidence = categoryExplanationResult?.evidence?.find((entry) => entry.category === category.name);
                        return <tr key={category.name}>
                          <th scope="row">{category.name}</th>
                          <td><button type="button" className="monthly-report-value-link" onClick={() => openCategoryPeriod(category.name, "current")} aria-label={`Show ${category.name} transactions for ${MONTH_NAMES[month]} ${year}, ${fmt(category.current)}`}>{fmt(category.current)}</button></td>
                          <td><button type="button" className="monthly-report-value-link" onClick={() => openCategoryPeriod(category.name, "prior")} aria-label={`Show ${category.name} transactions for ${MONTH_NAMES[priorMonth]} ${priorYear}, ${fmt(category.prior)}`}>{fmt(category.prior)}</button></td>
                          <td className="monthly-report-average-value">{category.recent_three_month_average == null ? "—" : fmt(category.recent_three_month_average)}</td>
                          <td className="monthly-report-average-value">{category.all_data_monthly_average == null ? "—" : fmt(category.all_data_monthly_average)}</td>
                          <td className="monthly-report-explanation-cell">
                            {explanation ? <>
                              <p>{explanation}</p>
                              {evidence && (evidence.merchant_changes.length > 0 || evidence.largest_current_transactions.length > 0 || evidence.largest_baseline_transactions.length > 0) && <details className="monthly-report-inline-evidence">
                                <summary>View merchant and transaction evidence</summary>
                                <div className="monthly-report-explanation-evidence">
                                  {evidence.baseline_months.length > 0 && <>
                                    <strong>Category spend in the comparison months</strong>
                                    <div className="monthly-report-month-pattern">{evidence.baseline_months.map((baselineMonth) => <div key={baselineMonth.month}>
                                      <b>{MONTH_NAMES[Number(baselineMonth.month.slice(5))].slice(0, 3)} {baselineMonth.month.slice(0, 4)}</b>
                                      <span>{baselineMonth.observed_activity ? `${fmt(baselineMonth.category_gross_purchases)} · ${baselineMonth.category_transaction_count} category transactions` : "No observed transaction activity"}</span>
                                    </div>)}</div>
                                    {evidence.baseline_month_count === 3 && evidence.baseline_category_median != null && evidence.baseline_category_range && <span className="monthly-report-baseline-range">
                                      Three-month median {fmt(evidence.baseline_category_median)} · range {fmt(evidence.baseline_category_range[0])}–{fmt(evidence.baseline_category_range[1])}
                                    </span>}
                                  </>}
                                  {evidence.merchant_changes.length > 0 && <>
                                    <strong>Merchant contributions</strong>
                                    <div className="monthly-report-driver-list">{evidence.merchant_changes.slice(0, 5).map((driver) => <div key={driver.merchant}>
                                      <span>{driver.merchant}</span><small>{fmt(driver.current_amount)} this month · {driver.baseline_monthly_average == null ? "no baseline" : `${fmt(driver.baseline_monthly_average)}/mo baseline`}; active in {driver.baseline_active_month_count}/{evidence.baseline_month_count} months<br />{driver.baseline_month_amounts.map((value) => `${MONTH_NAMES[Number(value.month.slice(5))].slice(0, 3)} ${value.observed_activity ? fmt(value.amount) : "no observed data"}`).join(" · ")}</small><b className={(driver.change ?? 0) >= 0 ? "is-increase" : "is-decrease"}>{driver.change == null ? "—" : `${driver.change > 0 ? "+" : driver.change < 0 ? "−" : ""}${fmt(Math.abs(driver.change))}`}</b>
                                    </div>)}</div>
                                  </>}
                                  {evidence.largest_baseline_transactions.length > 0 && <>
                                    <strong>Largest purchases in the comparison window</strong>
                                    <div className="monthly-report-example-list">{evidence.largest_baseline_transactions.slice(0, 3).map((transaction, index) => <div key={`${transaction.date}-${transaction.merchant}-${index}`}>
                                      <time>{transaction.date}</time><span>{transaction.merchant}{transaction.description && transaction.description !== transaction.merchant ? ` · ${transaction.description}` : ""}</span><b>{fmt(transaction.amount)}</b>
                                    </div>)}</div>
                                  </>}
                                  {evidence.largest_current_transactions.length > 0 && <>
                                    <strong>Largest transactions this month</strong>
                                    <div className="monthly-report-example-list">{evidence.largest_current_transactions.slice(0, 4).map((transaction, index) => <div key={`${transaction.date}-${transaction.merchant}-${index}`}>
                                      <time>{transaction.date}</time><span>{transaction.merchant}{transaction.description && transaction.description !== transaction.merchant ? ` · ${transaction.description}` : ""}</span><b>{fmt(transaction.amount)}</b>
                                    </div>)}</div>
                                  </>}
                                </div>
                              </details>}
                            </> : delta == null ? <span className="monthly-report-explanation-muted">{categoryComparison === "recent3" ? `Recent baseline unavailable (${recentObservedCount}/3 months observed)` : "No prior-month baseline"}</span>
                              : Math.abs(delta) < 0.01 ? <span className="monthly-report-explanation-muted">No material difference</span>
                                : categoryExplanationError ? <span className="monthly-report-explanation-muted">Explanation unavailable</span>
                                  : categoryExplanationResult ? <span className="monthly-report-explanation-muted">No clear driver identified</span>
                                    : <span className="monthly-report-explanation-muted">Generate explanations to see potential drivers</span>}
                          </td>
                        </tr>;
                      })()
                    ))}</tbody>
                  </table>
                </div>
            </div>
          )}

          {/* 4. Top merchants */}
          {report.merchants.length > 0 && (
            <div style={card}>
              <div style={sectionTitle}>Top Merchants by Gross Purchases</div>
              {report.merchants.map((m, i) => {
                const pad = (n: number) => String(n).padStart(2, "0");
                const from = `${year}-${pad(month)}-01`;
                const lastDay = new Date(year, month, 0).getDate();
                const to = `${year}-${pad(month)}-${pad(lastDay)}`;
                return (
                  <div
                    key={m.name}
                    onClick={() => openMerchantPeriod(m.name, from, to)}
                    style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "10px 0", borderBottom: i < report.merchants.length - 1 ? "1px solid #312e81" : "none",
                      cursor: "pointer",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.opacity = "0.75")}
                    onMouseLeave={(e) => (e.currentTarget.style.opacity = "1")}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <span style={{ fontSize: 12, color: "#6b7280", minWidth: 18 }}>{i + 1}</span>
                      <span style={{ color: "#374151" }}>{m.name}</span>
                    </div>
                    <span style={{ color: "#5b4bb7", fontWeight: 600 }}>{fmt(m.total)}</span>
                  </div>
                );
              })}
            </div>
          )}

          {/* 5. Subscriptions due */}
          {report.subscriptions_due.length > 0 && (
            <div style={card}>
              <div style={sectionTitle}>Subscriptions Renewing Soon</div>
              {report.subscriptions_due.map((s, i) => (
                <div
                  key={s.description + s.next_date}
                  onClick={() => navigate("/subscriptions")}
                  style={{
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    padding: "10px 0",
                    borderBottom: i < report.subscriptions_due.length - 1 ? "1px solid #312e81" : "none",
                    cursor: "pointer",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.opacity = "0.75")}
                  onMouseLeave={(e) => (e.currentTarget.style.opacity = "1")}
                >
                  <div>
                    <span style={{ color: "#92400e", marginRight: 8 }}>⚠</span>
                    <span style={{ color: "#374151" }}>{s.description}</span>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ color: "#5b4bb7", fontWeight: 600 }}>{fmt(s.amount)}</div>
                    <div style={{ fontSize: 11, color: "#6b7280" }}>{s.next_date}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {drilldown && <div className="report-drilldown-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setDrilldown(null); }}>
        <section className="report-drilldown-panel" role="dialog" aria-modal="true" aria-labelledby="report-drilldown-title">
          <header className="report-drilldown-header">
            <div><div className="report-drilldown-kicker">MONTHLY REPORT EVIDENCE</div><h2 id="report-drilldown-title">{drilldown.category ?? drilldown.merchant} · {drilldown.label}</h2></div>
            <button ref={closeDrilldownButton} type="button" onClick={() => setDrilldown(null)} aria-label="Close transaction details">×</button>
          </header>
          <div className="report-drilldown-summary"><strong>{drilldownTransactions.length} transactions</strong><span>{fmt(drilldownTotal)} gross purchases</span><span>{drilldown.date_from} – {drilldown.date_to}</span></div>
          {drilldownLoading ? <p role="status" className="report-drilldown-empty">Loading matching transactions…</p>
            : drilldownError ? <p role="alert" className="report-drilldown-empty">{drilldownError}</p>
              : drilldownTransactions.length === 0 ? <p className="report-drilldown-empty">No transactions found for this category and month.</p>
                : <div className="report-drilldown-list">{drilldownTransactions.map((transaction) => <article key={transaction.id}>
                  <time>{transaction.date}</time><div><strong>{transaction.merchant_name || transaction.description}</strong>{transaction.merchant_name && transaction.merchant_name !== transaction.description && <small>{transaction.description}</small>}</div><span>{transaction.source}</span><b>{fmt(transaction.amount)}</b>
                </article>)}</div>}
          <footer><button type="button" onClick={() => setDrilldown(null)}>Back to monthly report</button></footer>
        </section>
      </div>}
    </div>
  );
}
