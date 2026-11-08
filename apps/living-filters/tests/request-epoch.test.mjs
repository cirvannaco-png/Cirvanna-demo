import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequestEpoch } from "../src/request-epoch.mjs";

test("only the newest asynchronous request remains current", () => {
  const requests = createRequestEpoch();
  const first = requests.begin();
  const second = requests.begin();

  assert.equal(requests.isCurrent(first), false);
  assert.equal(requests.isCurrent(second), true);
});

test("invalidation cancels a pending request", () => {
  const requests = createRequestEpoch();
  const pending = requests.begin();

  requests.invalidate();

  assert.equal(requests.isCurrent(pending), false);
});

test("invalid epoch values are never current", () => {
  const requests = createRequestEpoch();
  const current = requests.begin();

  assert.equal(requests.isCurrent(current), true);
  assert.equal(requests.isCurrent("1"), false);
  assert.equal(requests.isCurrent(NaN), false);
  assert.equal(requests.isCurrent(-1), false);
});

test("camera integration disposes streams returned after user intent changed", () => {
  const app = readFileSync(new URL("../src/app.mjs", import.meta.url), "utf8");
  assert.match(app, /const requestEpoch = cameraRequestEpoch\.begin\(\)/);
  assert.match(app, /if \(!cameraRequestEpoch\.isCurrent\(requestEpoch\)\) \{[\s\S]*?for \(const track of stream\.getTracks\(\)\) track\.stop\(\)/);
  assert.match(app, /cameraRequestEpoch\.invalidate\(\)/);
});


test("hiding the page invalidates pending camera access through the common cleanup path", () => {
  const app = readFileSync(new URL("../src/app.mjs", import.meta.url), "utf8");
  assert.match(app, /document\.addEventListener\("visibilitychange",\s*\(\) => \{[\s\S]*?if \(document\.hidden\) stopCamera\(\)/);
  assert.match(app, /function stopCamera\(\) \{[\s\S]*?cameraRequestEpoch\.invalidate\(\)/);
});


test("late video.play completion cannot revive an invalidated camera session", () => {
  const app = readFileSync(new URL("../src/app.mjs", import.meta.url), "utf8");
  assert.match(app, /await elements\.video\.play\(\);[\s\S]*?if \(!cameraRequestEpoch\.isCurrent\(requestEpoch\) \|\| cameraStream !== stream\)/);
  assert.match(app, /if \(!cameraRequestEpoch\.isCurrent\(requestEpoch\) \|\| cameraStream !== stream\)[\s\S]*?showSource\("camera"\)/);
});

test("unexpected video track termination invokes the common camera cleanup path", () => {
  const app = readFileSync(new URL("../src/app.mjs", import.meta.url), "utf8");
  assert.match(app, /track\.addEventListener\("ended",[\s\S]*?if \(cameraStream !== stream\) return;[\s\S]*?stopCamera\(\)/);
});
