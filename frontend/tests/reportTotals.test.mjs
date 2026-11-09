import test from "node:test";
import assert from "node:assert/strict";
import { monthlyReportTotals } from "../src/api/reportTotals.ts";

test("maps report API spending fields to headline totals", () => {
  assert.deepEqual(monthlyReportTotals({
    total: 1369.71,
    gross_purchases: 1369.71,
    refunds: 573.91,
    net_spending: 795.8,
  }), {
    gross: 1369.71,
    refunds: 573.91,
    net: 795.8,
  });
});
