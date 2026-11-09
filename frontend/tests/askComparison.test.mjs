import test from "node:test";
import assert from "node:assert/strict";
import { getAskComparisonView } from "../src/api/askComparison.ts";

test("SQL comparison without transaction criteria renders as query evidence", () => {
  const comparison = {
    source: "sql",
    evidence: { sql: "SELECT city, SUM(amount) AS total FROM transactions GROUP BY city" },
    columns: ["city", "total"],
    rows: [{ city: "Oakland", total: 125.5 }],
  };

  assert.deepEqual(getAskComparisonView(comparison), {
    kind: "sql",
    sql: comparison.evidence.sql,
    columns: comparison.columns,
    rows: comparison.rows,
  });
});

test("transaction comparisons retain criteria and metric presentation", () => {
  const comparison = {
    criteria: { city: "Oakland" }, match_count: 2,
    gross_purchases: 130, refunds: 4.5, net_spending: 125.5,
  };

  assert.deepEqual(getAskComparisonView(comparison), {
    kind: "transactions",
    ...comparison,
  });
});
