import test from "node:test";
import assert from "node:assert/strict";
import {
  LANDMARK_FRAME_VERSION,
  createLandmarkFrameValidator,
  validateLandmarkFrame,
} from "../src/landmark-frame-contract.mjs";

function makeFrame(overrides = {}) {
  return {
    version: LANDMARK_FRAME_VERSION,
    topologyId: "test-face-topology-v1",
    timestampMs: 100,
    sourceWidth: 640,
    sourceHeight: 480,
    faces: [{
      confidence: 0.98,
      landmarks: [
        { x: 0.2, y: 0.3, z: -0.1 },
        { x: 0.5, y: 0.6, z: 0 },
      ],
    }],
    ...overrides,
  };
}

const smallTopology = { minLandmarks: 2, maxLandmarks: 2, expectedTopologyId: "test-face-topology-v1" };

test("accepts a well-formed canonical frame without mutating it", () => {
  const frame = makeFrame();
  const result = validateLandmarkFrame(frame, smallTopology);
  assert.equal(result.ok, true);
  assert.equal(result.frame, frame);
  assert.equal(frame.faces[0].landmarks.length, 2);
});

test("rejects missing or unsupported contract versions", () => {
  assert.equal(validateLandmarkFrame(null).reason, "frame-not-object");
  assert.equal(validateLandmarkFrame(makeFrame({ version: 99 })).reason, "unsupported-version");
});

test("rejects topology mismatch instead of interpreting foreign landmark indices", () => {
  assert.equal(
    validateLandmarkFrame(makeFrame({ topologyId: "other-v2" }), smallTopology).reason,
    "topology-mismatch",
  );
});

test("rejects invalid timestamps and source dimensions", () => {
  assert.equal(validateLandmarkFrame(makeFrame({ timestampMs: NaN })).reason, "invalid-timestamp");
  assert.equal(validateLandmarkFrame(makeFrame({ timestampMs: -1 })).reason, "invalid-timestamp");
  assert.equal(validateLandmarkFrame(makeFrame({ sourceWidth: 0 })).reason, "invalid-source-dimensions");
  assert.equal(validateLandmarkFrame(makeFrame({ sourceHeight: 1.5 })).reason, "invalid-source-dimensions");
});

test("rejects excess faces and invalid confidence values", () => {
  const frame = makeFrame({ faces: [makeFrame().faces[0], makeFrame().faces[0]] });
  assert.equal(validateLandmarkFrame(frame, smallTopology).reason, "invalid-face-count");
  assert.equal(
    validateLandmarkFrame(makeFrame({ faces: [{ confidence: 1.1, landmarks: [{ x: 0, y: 0, z: 0 }] }] })).reason,
    "invalid-confidence",
  );
});

test("rejects empty, undersized, oversized, or malformed landmark sets", () => {
  assert.equal(validateLandmarkFrame(makeFrame({ faces: [{ landmarks: [] }] }), smallTopology).reason, "invalid-landmark-count");
  assert.equal(
    validateLandmarkFrame(makeFrame({ faces: [{ landmarks: [{ x: 0.2, y: 0.2, z: 0 }] }] }), smallTopology).reason,
    "invalid-landmark-count",
  );
  assert.equal(
    validateLandmarkFrame(makeFrame({ faces: [{ landmarks: [{ x: 0.2, y: 0.2, z: 0 }, { x: 0.2, y: 0.2, z: 0 }, { x: 0.2, y: 0.2, z: 0 }] }] }), smallTopology).reason,
    "invalid-landmark-count",
  );
});

test("rejects non-finite and out-of-range normalized coordinates", () => {
  for (const point of [
    { x: -0.01, y: 0.5, z: 0 },
    { x: 0.5, y: 1.01, z: 0 },
    { x: 0.5, y: 0.5, z: Infinity },
    { x: NaN, y: 0.5, z: 0 },
  ]) {
    const frame = makeFrame({ faces: [{ landmarks: [point, { x: 0.2, y: 0.3, z: 0 }] }] });
    assert.equal(validateLandmarkFrame(frame, smallTopology).reason, "invalid-landmark-coordinate");
  }
});

test("live validator rejects duplicate/out-of-order timestamps and can reset per source", () => {
  const validator = createLandmarkFrameValidator(smallTopology);
  assert.equal(validator.validate(makeFrame({ timestampMs: 10 })).ok, true);
  assert.equal(validator.validate(makeFrame({ timestampMs: 10 })).reason, "stale-timestamp");
  assert.equal(validator.validate(makeFrame({ timestampMs: 9 })).reason, "stale-timestamp");
  assert.equal(validator.validate(makeFrame({ timestampMs: 11 })).ok, true);
  validator.reset();
  assert.equal(validator.validate(makeFrame({ timestampMs: 1 })).ok, true);
});

test("an empty face list is valid and means no overlay should be rendered", () => {
  const result = validateLandmarkFrame(makeFrame({ faces: [] }), smallTopology);
  assert.equal(result.ok, true);
  assert.equal(result.frame.faces.length, 0);
});
