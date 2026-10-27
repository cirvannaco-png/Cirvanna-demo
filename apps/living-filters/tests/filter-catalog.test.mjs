import test from "node:test";
import assert from "node:assert/strict";
import { FILTERS, FILTER_BY_ID, getFilterById } from "../src/filter-catalog.mjs";

test("filter IDs are unique and stable", () => {
  const ids = FILTERS.map((filter) => filter.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.deepEqual(ids, ["original", "golden-hour", "dewy-light", "rose-tint", "editorial", "aurora", "starlight", "film"]);
});

test("every filter exposes the presentation contract", () => {
  for (const filter of FILTERS) {
    assert.match(filter.id, /^[a-z0-9]+(?:-[a-z0-9]+)*$/);
    assert.ok(filter.name.trim().length > 0);
    assert.ok(filter.category.trim().length > 0);
    assert.ok(filter.description.trim().length > 0);
    assert.ok(typeof filter.cssFilter === "string");
    assert.ok(["none", "soft-glow", "rose-haze", "aurora", "starlight"].includes(filter.effect));
  }
});

test("catalog and entries are immutable", () => {
  assert.equal(Object.isFrozen(FILTERS), true);
  for (const filter of FILTERS) assert.equal(Object.isFrozen(filter), true);
  assert.throws(() => FILTERS.push({ id: "injected" }), TypeError);
});

test("unknown filter IDs fall back to Original", () => {
  assert.equal(getFilterById("not-a-real-filter"), FILTER_BY_ID.original);
  assert.equal(getFilterById("original").id, "original");
});

test("visual filter metadata does not claim skin analysis or face tracking", () => {
  assert.equal(FILTERS.some((filter) => /diagnos|clinical|face.track|skin analysis/i.test(filter.description)), false);
  assert.equal(FILTERS.every((filter) => !("provider" in filter)), true);
});