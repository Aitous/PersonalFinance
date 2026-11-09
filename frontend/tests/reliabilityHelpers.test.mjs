import test from "node:test";
import assert from "node:assert/strict";
import {
  monthlyAverageRange,
  monthlyAverageRangeError,
  readMonthlyAverageResponse,
  previewRequestKey,
  reportPeriodRange,
  samePreviewRequest,
} from "../src/api/reliabilityHelpers.ts";

test("monthly-average custom ranges reject reversed dates before requesting data", () => {
  assert.equal(monthlyAverageRangeError("2026-10-20", "2026-10-19"), "Start date must be on or before end date.");
  assert.equal(monthlyAverageRangeError("2026-10-19", "2026-10-19"), null);
  assert.equal(monthlyAverageRangeError("", "2026-10-19"), null);
});

test("monthly-average requests treat non-2xx validation responses as errors", async () => {
  await assert.rejects(
    readMonthlyAverageResponse({ ok: false, json: async () => ({ detail: "date_from must be before date_to" }) }),
    /date_from must be before date_to/,
  );
});

test("report prior-period ranges roll January back to December of the prior year", () => {
  assert.deepEqual(reportPeriodRange(2026, 1, "prior"), {
    date_from: "2025-12-01", date_to: "2025-12-31",
  });
  assert.deepEqual(reportPeriodRange(2024, 2, "current"), {
    date_from: "2024-02-01", date_to: "2024-02-29",
  });
  assert.equal(reportPeriodRange(2026, 1, "name"), null);
});

test("monthly average drilldowns use the returned covered period", () => {
  assert.deepEqual(monthlyAverageRange("dining", "2025-10-01", "2025-12-31"), {
    category: "dining", date_from: "2025-10-01", date_to: "2025-12-31",
  });
  assert.deepEqual(monthlyAverageRange("dining"), { category: "dining" });
});

test("preview identity includes the exact file object, bank, and account", () => {
  const file = {};
  const sameObject = previewRequestKey(file, "chase", "account-1");
  assert.equal(samePreviewRequest(sameObject, previewRequestKey(file, "chase", "account-1")), true);
  assert.equal(samePreviewRequest(sameObject, previewRequestKey({}, "chase", "account-1")), false);
  assert.equal(samePreviewRequest(sameObject, previewRequestKey(file, "amex", "account-1")), false);
  assert.equal(samePreviewRequest(sameObject, previewRequestKey(file, "chase", "account-2")), false);
  assert.equal(samePreviewRequest(null, sameObject), false);
});
