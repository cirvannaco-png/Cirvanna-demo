import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const root = new URL("../", import.meta.url);
const read = (path) => readFileSync(new URL(path, root), "utf8");

test("runtime and model versions are immutable pins with expected integrity metadata", () => {
  const manifest = JSON.parse(read("vision-assets.manifest.json"));
  assert.equal(manifest.runtime.package, "@mediapipe/tasks-vision");
  assert.equal(manifest.runtime.version, "0.10.21");
  assert.match(manifest.runtime.tarballIntegrity, /^sha512-[A-Za-z0-9+/]{86}==$/);
  assert.equal(manifest.runtime.license, "Apache-2.0");
  assert.equal(manifest.runtime.tarballUrl.includes("@latest"), false);
  assert.equal(manifest.models.length, 2);
  for (const model of manifest.models) {
    assert.match(model.sha256, /^[a-f0-9]{64}$/);
    assert.match(model.path, /^models\/[a-z0-9_.-]+$/);
    assert.equal(model.license, "Apache-2.0");
    assert.match(model.sourceUrl, /^https:\/\/storage\.googleapis\.com\/mediapipe-models\//);
  }
});

test("the shipped application requests only local model/runtime URLs", () => {
  const html = read("index.html");
  const worker = read("src/vision-worker.mjs");
  const app = read("src/app.mjs");
  assert.doesNotMatch(html, /<script[^>]+src=["']https?:\/\//i);
  assert.doesNotMatch(worker, /https?:\/\//i);
  assert.doesNotMatch(app, /\bfetch\s*\(|XMLHttpRequest|https?:\/\//i);
  assert.match(worker, /new URL\("\.\.\/vendor\/mediapipe\/wasm\/", workerBaseUrl\)/);
  assert.match(worker, /new URL\("\.\.\/models\/face_landmarker\.task", workerBaseUrl\)/);
  assert.match(worker, /new URL\("\.\.\/models\/hair_segmenter\.tflite", workerBaseUrl\)/);
});

test("MediaPipe executes in a classic bundled worker so its WASM glue can use importScripts", () => {
  const app = read("src/app.mjs");
  const worker = read("src/vision-worker.mjs");
  assert.match(app, /new Worker\(new URL\("\.\/vision-worker\.bundle\.js", import\.meta\.url\)/);
  assert.doesNotMatch(app, /type:\s*["']module["']/);
  assert.match(worker, /self\.location\.href/);
});

test("CSP allows same-origin workers and WASM compilation but forbids remote fallback and general eval", () => {
  const html = read("index.html");
  const csp = html.match(/http-equiv="Content-Security-Policy" content="([^"]+)"/i)?.[1];
  assert.ok(csp, "missing CSP");
  assert.match(csp, /default-src 'self'/);
  assert.match(csp, /script-src 'self' 'wasm-unsafe-eval'/);
  assert.match(csp, /connect-src 'self'/);
  assert.match(csp, /worker-src 'self'/);
  assert.match(csp, /img-src 'self' blob: data:/);
  assert.match(csp, /media-src 'self' blob:/);
  assert.doesNotMatch(csp, /(?:^|\s)'unsafe-eval'(?:\s|;|$)/);
  assert.doesNotMatch(csp, /https?:\/\//);
});

test("third-party notice and preparation/verification scripts are present", () => {
  const notice = read("THIRD_PARTY_NOTICES.md");
  const prep = read("scripts/prepare-vision-assets.mjs");
  const verify = read("scripts/verify-vision-assets.mjs");
  const license = read("third-party/mediapipe-LICENSE");
  assert.match(notice, /Apache License 2\.0/);
  assert.match(notice, /sha-?256/i);
  assert.match(prep, /tarballIntegrity/);
  assert.match(prep, /SHA-256 mismatch/);
  assert.match(prep, /mediapipe-LICENSE/);
  assert.match(verify, /Runtime\/WASM integrity mismatch/);
  assert.match(verify, /Model SHA-256 or size mismatch/);
  assert.match(license, /Apache License/);
  assert.match(license, /TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION/);
});

test("face renderer and worker stay isolated from DermalSight inputs and remote calls", () => {
  const worker = read("src/vision-worker.mjs");
  const renderer = read("src/face-renderer.mjs");
  assert.doesNotMatch(worker + renderer, /dermalsight|skin diagnosis|diagnos/i);
  assert.doesNotMatch(worker + renderer, /\bfetch\s*\(|XMLHttpRequest|https?:\/\//i);
  assert.match(renderer, /drawTrackedMakeup/);
  assert.match(renderer, /drawTrackedAccessory/);
  assert.match(renderer, /makeHairTintPixels/);
});

test("worker discards stale initialization results and closes superseded models", () => {
  const worker = read("src/vision-worker.mjs");
  assert.match(worker, /async function initialise\(requestedSession\)/);
  assert.match(worker, /const isCurrent = \(\) => !disposed && requestedSession === sessionToken/);
  assert.match(worker, /if \(!isCurrent\(\)\) return;/);
  assert.match(worker, /nextFaceLandmarker\?\.close/);
  assert.match(worker, /nextHairSegmenter\?\.close/);
  assert.match(worker, /sessionToken !== message\.session \|\| disposed/);
});
