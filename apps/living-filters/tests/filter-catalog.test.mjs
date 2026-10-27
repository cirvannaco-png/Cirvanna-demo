import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
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

test("the browser shell exposes every element required by the application", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const ids = [
    "stage", "camera-preview", "photo-preview", "stage-empty", "stage-label",
    "photo-input", "start-camera", "stop-camera", "capture", "status",
    "filter-grid", "filter-count", "selected-name", "selected-description",
  ];
  for (const id of ids) assert.ok(html.includes('id="' + id + '"'), "missing required element: " + id);
  assert.match(html, /type="module" src="\.\/src\/app\.mjs"/);
});

test("every catalogue entry has a stylesheet rule for preview rendering", () => {
  const css = readFileSync(new URL("../styles.css", import.meta.url), "utf8");
  for (const filter of FILTERS) {
    assert.ok(css.includes('.stage[data-filter="' + filter.id + '"] .media'), "missing preview CSS for " + filter.id);
  }
});

test("the browser app has no network upload or remote script integration", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const app = readFileSync(new URL("../src/app.mjs", import.meta.url), "utf8");
  assert.doesNotMatch(html, /<script[^>]+src=["']https?:\/\//i);
  assert.doesNotMatch(app, /\bfetch\s*\(|XMLHttpRequest|https?:\/\//i);
});
