import test from "node:test";
import assert from "node:assert/strict";
import { readTransactionFilters, writeTransactionFilters } from "../src/api/transactionFilters.ts";

test("reads legacy report aliases and writes the canonical URL contract", () => {
  const filters = readTransactionFilters(new URLSearchParams(
    "search=Coffee&dateFrom=2026-01-01&dateTo=2026-01-31&merchant=Blue%20Bottle&category=dining",
  ));

  assert.deepEqual(filters, {
    q: "Coffee", merchant: "Blue Bottle", category: "dining",
    date_from: "2026-01-01", date_to: "2026-01-31",
  });
  assert.equal(writeTransactionFilters(filters).toString(), "q=Coffee&merchant=Blue+Bottle&category=dining&date_from=2026-01-01&date_to=2026-01-31");
});

test("preserves advanced filters, false booleans, and zero amounts through refresh parsing", () => {
  const original = {
    ids: "a,b", source: "chase", min_amount: "0", is_online: "false",
    is_subscription: "true", tx_type: "all", search_mode: "keyword", sort: "amount", sort_dir: "asc",
  };
  const url = writeTransactionFilters(original);
  assert.deepEqual(readTransactionFilters(url), original);
  assert.equal(url.get("is_online"), "false");
  assert.equal(url.get("min_amount"), "0");
});

test("omits defaults so clearing filters returns to a clean URL", () => {
  assert.equal(writeTransactionFilters({ tx_type: "spending", search_mode: "hybrid", sort: "date", sort_dir: "desc" }).toString(), "");
});
