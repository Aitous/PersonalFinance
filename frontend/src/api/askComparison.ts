import type { TransactionQuestionComparison } from "./client";

export function getAskComparisonView(comparison: TransactionQuestionComparison) {
  if (comparison.source === "sql") {
    return {
      kind: "sql" as const,
      columns: comparison.columns,
      rows: comparison.rows,
      sql: comparison.evidence.sql,
    };
  }
  return { kind: "transactions" as const, ...comparison };
}
