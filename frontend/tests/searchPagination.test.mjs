import test from "node:test";
import assert from "node:assert/strict";
import { fetchAllSearchResults } from "../src/api/searchPagination.ts";

test("fetches every search result in pages for complete CSV export", async () => {
  const values = Array.from({ length: 7 }, (_, index) => `tx-${index}`);
  const requests = [];
  const results = await fetchAllSearchResults(async (offset, limit) => {
    requests.push({ offset, limit });
    return { results: values.slice(offset, offset + limit), total_results: values.length };
  }, 3);

  assert.deepEqual(results, values);
  assert.deepEqual(requests, [
    { offset: 0, limit: 3 },
    { offset: 3, limit: 3 },
    { offset: 6, limit: 3 },
  ]);
});

test("stops if a page is empty to avoid an infinite export loop", async () => {
  const results = await fetchAllSearchResults(async () => ({ results: [], total_results: 5 }), 2);
  assert.deepEqual(results, []);
});
