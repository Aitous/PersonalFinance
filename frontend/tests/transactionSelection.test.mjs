import test from "node:test";
import assert from "node:assert/strict";
import { toggleVisibleSelection, selectionTotalCents } from "../src/api/transactionSelection.ts";

test("selecting and clearing visible rows preserves selections from other pages", () => {
  const previous = { a: { id: "a", amount: 10 } };
  const visible = [{ id: "b", amount: 3.25 }, { id: "c", amount: -1.10 }];
  const selected = toggleVisibleSelection(previous, visible, true);
  assert.deepEqual(Object.keys(selected).sort(), ["a", "b", "c"]);
  assert.equal(selectionTotalCents(selected), 1215);
  assert.deepEqual(toggleVisibleSelection(selected, visible, false), previous);
});

test("selection total uses signed cents without floating-point drift", () => {
  assert.equal(selectionTotalCents({ a: { id: "a", amount: 0.1 }, b: { id: "b", amount: 0.2 }, c: { id: "c", amount: -0.05 } }), 25);
});
