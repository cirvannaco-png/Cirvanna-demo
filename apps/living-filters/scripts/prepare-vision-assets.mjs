#!/usr/bin/env node
/**
 * Prepare pinned, local-only MediaPipe assets for Living Filters.
 *
 * This command requires Node.js 20+ and network access during preparation.
 * The running app loads only same-origin files and does not fetch remote assets.
 * Generated binaries are intentionally excluded from source control; deployments
 * must run this preparation step during their build and publish the generated
 * vendor/ and models/ directories with the static app.
 */
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  copyFileSync, cpSync, existsSync, mkdirSync, readFileSync, readdirSync,
  rmSync, statSync, writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const appRoot = resolve(scriptDirectory, "..");
const manifest = JSON.parse(readFileSync(join(appRoot, "vision-assets.manifest.json"), "utf8"));

function sha256(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

function sha512Integrity(buffer) {
  return "sha512-" + createHash("sha512").update(buffer).digest("base64");
}

function fail(message) {
  throw new Error(message);
}

async function downloadPinnedAsset(asset, destination, maxBytes) {
  const response = await fetch(asset.sourceUrl, { redirect: "error", signal: AbortSignal.timeout(120000) });
  if (!response.ok) fail(`Download failed for ${asset.id}: HTTP ${response.status}`);
  const bytes = Buffer.from(await response.arrayBuffer());
  if (bytes.length === 0 || bytes.length > maxBytes) {
    fail(`Unexpected size for ${asset.id}: ${bytes.length} bytes`);
  }
  const digest = sha256(bytes);
  if (digest !== asset.sha256) {
    fail(`SHA-256 mismatch for ${asset.id}; expected ${asset.sha256}, received ${digest}. Asset not installed.`);
  }
  mkdirSync(dirname(destination), { recursive: true });
  const temporaryPath = destination + ".download";
  writeFileSync(temporaryPath, bytes, { flag: "w" });
  rmSync(destination, { force: true });
  // A same-directory rename is atomic on supported local filesystems.
  const { renameSync } = await import("node:fs");
  renameSync(temporaryPath, destination);
  return { path: asset.path, sizeBytes: bytes.length, sha256: digest };
}

function listFiles(directory) {
  if (!existsSync(directory)) return [];
  const files = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const absolute = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...listFiles(absolute));
    else if (entry.isFile()) files.push(absolute);
    else fail(`Unexpected non-file asset in ${directory}`);
  }
  return files;
}

async function main() {
  const temporaryRoot = join(tmpdir(), `cirvanna-living-filters-${process.pid}-${Date.now()}`);
  const packDirectory = join(temporaryRoot, "pack");
  const extractDirectory = join(temporaryRoot, "extract");
  const stagingDirectory = join(temporaryRoot, "stage");
  mkdirSync(packDirectory, { recursive: true });
  mkdirSync(extractDirectory, { recursive: true });
  mkdirSync(stagingDirectory, { recursive: true });

  try {
    const packJson = execFileSync("npm", [
      "pack", `${manifest.runtime.package}@${manifest.runtime.version}`,
      "--pack-destination", packDirectory, "--ignore-scripts", "--json",
    ], { cwd: packDirectory, encoding: "utf8", stdio: ["ignore", "pipe", "inherit"] });
    const packInfo = JSON.parse(packJson)[0];
    const tarballPath = join(packDirectory, packInfo.filename);
    const tarball = readFileSync(tarballPath);
    const actualIntegrity = sha512Integrity(tarball);
    if (actualIntegrity !== manifest.runtime.tarballIntegrity) {
      fail(`Runtime package integrity mismatch. Expected ${manifest.runtime.tarballIntegrity}; received ${actualIntegrity}.`);
    }

    execFileSync("tar", ["-xzf", tarballPath, "-C", extractDirectory], { stdio: "inherit" });
    const packageRoot = join(extractDirectory, "package");
    const runtimeSource = join(packageRoot, manifest.runtime.runtimeEntry);
    const wasmSource = join(packageRoot, manifest.runtime.wasmDirectory);
    if (!existsSync(runtimeSource) || !statSync(runtimeSource).isFile()) fail("Pinned runtime entry is missing from npm package.");
    if (!existsSync(wasmSource) || !statSync(wasmSource).isDirectory()) fail("Pinned WASM directory is missing from npm package.");
    const packageLicense = ["LICENSE", "LICENSE.md", "LICENSE.txt"].map((file) => join(packageRoot, file)).find(existsSync);
    if (!packageLicense) fail("Runtime package has no discoverable licence file; refusing installation.");

    const runtimeTarget = join(stagingDirectory, "vendor", "mediapipe");
    mkdirSync(runtimeTarget, { recursive: true });
    copyFileSync(runtimeSource, join(runtimeTarget, manifest.runtime.runtimeEntry));
    cpSync(wasmSource, join(runtimeTarget, "wasm"), { recursive: true });
    copyFileSync(packageLicense, join(runtimeTarget, "LICENSE"));

    const installedModels = [];
    for (const model of manifest.models) {
      const target = join(stagingDirectory, model.path);
      installedModels.push(await downloadPinnedAsset(model, target, 32 * 1024 * 1024));
    }

    const vendorRoot = join(stagingDirectory, "vendor", "mediapipe");
    const runtimeFiles = listFiles(vendorRoot).map((absolute) => {
      const bytes = readFileSync(absolute);
      return {
        path: relative(stagingDirectory, absolute).split(sep).join("/"),
        sizeBytes: bytes.length,
        sha256: sha256(bytes),
      };
    });
    const installedLock = {
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      runtime: {
        package: manifest.runtime.package,
        version: manifest.runtime.version,
        npmIntegrity: actualIntegrity,
        license: manifest.runtime.license,
        files: runtimeFiles,
      },
      models: installedModels,
      policy: {
        downloadsOccurOnlyDuringPreparation: true,
        appRuntimeRemoteRequestsAllowed: false,
        mediaOrLandmarksPersistedByThisFeature: false,
      },
    };
    writeFileSync(join(stagingDirectory, "vendor", "mediapipe", "assets-lock.json"), JSON.stringify(installedLock, null, 2) + "\n");

    // Replace generated directories only after every download and integrity check succeeds.
    for (const generated of ["vendor/mediapipe", "models"]) {
      rmSync(join(appRoot, generated), { recursive: true, force: true });
    }
    cpSync(join(stagingDirectory, "vendor"), join(appRoot, "vendor"), { recursive: true });
    cpSync(join(stagingDirectory, "models"), join(appRoot, "models"), { recursive: true });

    console.log(`Prepared ${runtimeFiles.length} pinned runtime/WASM files and ${installedModels.length} model files.`);
    console.log("Installed local-only assets under apps/living-filters/vendor/ and apps/living-filters/models/.");
    console.log("No runtime CDN or remote model URL is configured. Run the validation workflow before release.");
  } finally {
    rmSync(temporaryRoot, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(`Asset preparation failed: ${error?.message ?? error}`);
  process.exitCode = 1;
});
