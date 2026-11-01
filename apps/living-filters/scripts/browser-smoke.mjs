#!/usr/bin/env node
/**
 * Chromium smoke test for the prepared, local-only Vision runtime.
 * Requires Playwright installed in apps/living-filters/node_modules and generated
 * assets from prepare-vision-assets.mjs. No externally hosted resources allowed.
 */
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { existsSync, statSync } from "node:fs";
import { dirname, extname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const mimeTypes = new Map([
  [".html", "text/html; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".mjs", "text/javascript; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".wasm", "application/wasm"],
  [".task", "application/octet-stream"],
  [".tflite", "application/octet-stream"],
  [".json", "application/json; charset=utf-8"],
]);

for (const required of [
  "vendor/mediapipe/vision_bundle.mjs",
  "src/vision-worker.bundle.js",
  "models/face_landmarker.task",
  "models/hair_segmenter.tflite",
]) {
  const path = join(appRoot, required);
  if (!existsSync(path) || !statSync(path).isFile()) {
    throw new Error("Missing generated local asset: " + required + ". Run prepare-vision-assets.mjs first.");
  }
}

const server = createServer(async (request, response) => {
  try {
    const parsed = new URL(request.url, "http://127.0.0.1");
    if (parsed.pathname === "/favicon.ico") {
      response.writeHead(204).end();
      return;
    }
    const requestedPath = decodeURIComponent(parsed.pathname === "/" ? "/index.html" : parsed.pathname);
    const path = resolve(appRoot, "." + requestedPath);
    if (!path.startsWith(appRoot + sep)) {
      response.writeHead(403).end("Forbidden");
      return;
    }
    const bytes = await readFile(path);
    response.writeHead(200, {
      "Content-Type": mimeTypes.get(extname(path)) ?? "application/octet-stream",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    });
    response.end(bytes);
  } catch {
    response.writeHead(404).end("Not found");
  }
});

const externalRequests = [];
const pageErrors = [];
let browser;
let status = "not-started";
try {
  await new Promise((resolveListen, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolveListen);
  });
  const address = server.address();
  const origin = `http://127.0.0.1:${address.port}`;
  browser = await chromium.launch({
    headless: true,
    args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", "--autoplay-policy=no-user-gesture-required"],
  });
  const context = await browser.newContext({ permissions: ["camera"] });
  const page = await context.newPage();
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") pageErrors.push("console: " + message.text());
  });
  await page.addInitScript(() => {
    window.__cspViolations = [];
    document.addEventListener("securitypolicyviolation", (event) => {
      window.__cspViolations.push({
        directive: event.violatedDirective,
        blockedURI: event.blockedURI,
      });
    });
  });
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (!["blob:", "data:"].includes(url.protocol) && url.origin !== origin) {
      externalRequests.push(request.url());
    }
  });

  await page.goto(origin, { waitUntil: "domcontentloaded" });
  const initialCsp = await page.locator('meta[http-equiv="Content-Security-Policy"]').getAttribute("content");
  assert.ok(initialCsp?.includes("connect-src 'self'"));
  assert.ok(initialCsp?.includes("worker-src 'self'"));

  await page.getByRole("button", { name: "Use camera" }).click();
  await page.waitForFunction(() => document.querySelector("#status")?.textContent.includes("Camera is active"), null, { timeout: 15000 });
  await page.locator("#ar-consent").check();
  await page.getByRole("button", { name: "Start on-device try-on" }).click();
  await page.waitForFunction(() => {
    const value = document.querySelector("#ar-status")?.textContent ?? "";
    return value.includes("Local face and hair models are ready") || value.includes("Could not load the local models") || value.includes("local vision worker failed");
  }, null, { timeout: 90000 });
  const initializationStatus = await page.locator("#ar-status").innerText();
  assert.match(initializationStatus, /Local face and hair models are ready/, "Local model initialization failed: " + initializationStatus + "; browser errors: " + pageErrors.join(" | "));

  // Disable browser networking after initialization. All subsequent frame
  // processing, masks and canvas effects must work from local in-memory state.
  await context.setOffline(true);
  await page.locator('[data-ar-mode="makeup"]').click();
  await page.waitForTimeout(1200);
  await page.locator('[data-ar-mode="hair-copper"]').click();
  await page.waitForTimeout(1200);
  assert.equal(await page.locator("#ar-overlay").isVisible(), true, "AR overlay canvas should become visible during selected effect");
  await page.getByRole("button", { name: "Stop tracking" }).click();
  await page.waitForFunction(() => (document.querySelector("#ar-status")?.textContent ?? "").includes("On-device face tracking is stopped"));

  const cspViolations = await page.evaluate(() => window.__cspViolations ?? []);
  assert.deepEqual(externalRequests, [], "Unexpected cross-origin network request(s): " + externalRequests.join(", "));
  assert.deepEqual(cspViolations, [], "Unexpected CSP violation(s): " + JSON.stringify(cspViolations));
  assert.deepEqual(pageErrors, [], "Unexpected browser page/console errors: " + pageErrors.join(" | "));
  status = "PASS: local models initialized, browser networking disabled, makeup/hair modes selected, local worker stopped, and zero cross-origin requests/CSP violations observed.";
  await context.close();
} catch (error) {
  status = "FAIL: " + (error?.stack ?? error);
  throw error;
} finally {
  if (browser) await browser.close();
  await new Promise((resolveClose) => server.close(resolveClose));
  console.log(status);
}
