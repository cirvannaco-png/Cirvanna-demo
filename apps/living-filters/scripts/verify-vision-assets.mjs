#!/usr/bin/env node
/**
 * Validate generated local MediaPipe runtime/model files against the pinned
 * manifest and generated asset lock. This requires a prior preparation step.
 */
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const manifest = JSON.parse(readFileSync(join(appRoot, "vision-assets.manifest.json"), "utf8"));
const lockPath = join(appRoot, "vendor", "mediapipe", "assets-lock.json");

function fail(message) {
  console.error("Vision asset verification failed: " + message);
  process.exitCode = 1;
}
function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}
function safeResolve(relativePath) {
  if (typeof relativePath !== "string" || relativePath.length === 0 || relativePath.includes("\\")
      || relativePath.startsWith("/") || relativePath.split("/").includes("..")) {
    throw new Error("Unsafe asset path in manifest/lock: " + String(relativePath));
  }
  const absolute = resolve(appRoot, relativePath);
  if (!absolute.startsWith(appRoot + sep)) throw new Error("Asset path escapes the app root: " + relativePath);
  return absolute;
}
function hashFile(path) {
  if (!existsSync(path) || !statSync(path).isFile()) throw new Error("Missing local asset: " + path);
  const bytes = readFileSync(path);
  return { sha256: sha256(bytes), sizeBytes: bytes.length };
}

function main() {
  if (!existsSync(lockPath)) {
    throw new Error("No generated asset lock found. Run node apps/living-filters/scripts/prepare-vision-assets.mjs on a network-enabled build machine first.");
  }
  const lock = JSON.parse(readFileSync(lockPath, "utf8"));
  if (lock.schemaVersion !== 1) throw new Error("Unsupported asset-lock schema.");
  if (lock.runtime?.package !== manifest.runtime.package
      || lock.runtime?.version !== manifest.runtime.version
      || lock.runtime?.npmIntegrity !== manifest.runtime.tarballIntegrity) {
    throw new Error("Runtime package/version/integrity does not match the pinned manifest.");
  }
  if (lock.runtime?.license !== manifest.runtime.license) throw new Error("Runtime licence mismatch.");
  if (!Array.isArray(lock.runtime.files) || lock.runtime.files.length < 3) throw new Error("Runtime lock is incomplete.");

  const lockedPaths = new Set();
  for (const asset of lock.runtime.files) {
    const path = safeResolve(asset.path);
    if (lockedPaths.has(asset.path)) throw new Error("Duplicate runtime path in lock: " + asset.path);
    lockedPaths.add(asset.path);
    const actual = hashFile(path);
    if (actual.sha256 !== asset.sha256 || actual.sizeBytes !== asset.sizeBytes) {
      throw new Error("Runtime/WASM integrity mismatch: " + asset.path);
    }
  }
  const bundlePath = "vendor/mediapipe/" + manifest.runtime.runtimeEntry;
  if (!lockedPaths.has(bundlePath)) throw new Error("Pinned runtime bundle is not covered by the asset lock.");
  if (!lockedPaths.has("vendor/mediapipe/LICENSE")) throw new Error("Runtime licence copy is absent from the lock.");
  const wasmRoot = safeResolve("vendor/mediapipe/wasm");
  if (!existsSync(wasmRoot) || !readdirSync(wasmRoot).some((name) => name.endsWith(".wasm"))) {
    throw new Error("No local WASM binary exists in the prepared runtime.");
  }

  const modelLock = new Map((lock.models ?? []).map((model) => [model.path, model]));
  for (const model of manifest.models) {
    const prepared = modelLock.get(model.path);
    if (!prepared || prepared.sha256 !== model.sha256) throw new Error("Model lock mismatch for " + model.id);
    const actual = hashFile(safeResolve(model.path));
    if (actual.sha256 !== model.sha256 || actual.sizeBytes !== prepared.sizeBytes) {
      throw new Error("Model SHA-256 or size mismatch for " + model.id);
    }
  }

  const html = readFileSync(join(appRoot, "index.html"), "utf8");
  const csp = html.match(/http-equiv="Content-Security-Policy" content="([^"]+)"/i)?.[1];
  if (!csp) throw new Error("Missing Content Security Policy.");
  for (const directive of [
    "default-src 'self'",
    "script-src 'self' 'wasm-unsafe-eval'",
    "connect-src 'self'",
    "worker-src 'self'",
    "img-src 'self' blob: data:",
    "media-src 'self' blob:",
  ]) {
    if (!csp.includes(directive)) throw new Error("CSP is missing required directive: " + directive);
  }
  if (/(?:^|\s)'unsafe-eval'(?:\s|;|$)/.test(csp)) {
    throw new Error("CSP may not enable general unsafe-eval.");
  }

  console.log("Verified pinned MediaPipe " + manifest.runtime.version);
  console.log("Verified " + lock.runtime.files.length + " runtime/WASM/licence files and " + manifest.models.length + " model files.");
  console.log("Verified restrictive local-origin CSP; no remote asset URL is configured by the running application.");
}

try {
  main();
} catch (error) {
  fail(error?.message ?? String(error));
}
