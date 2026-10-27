/**
 * Provider-neutral validation for face-landmark frames.
 *
 * This module does not detect faces or load a model. A provider adapter must
 * translate its output to this contract before a renderer can consume it.
 * Landmark coordinates x/y are normalized to [0, 1]; z is provider-relative.
 */
export const LANDMARK_FRAME_VERSION = 1;

const DEFAULT_LIMITS = Object.freeze({
  maxFaces: 1,
  minLandmarks: 1,
  maxLandmarks: 1000,
  maxDimension: 16384,
});

function failure(reason) {
  return Object.freeze({ ok: false, reason });
}

function isPositiveInteger(value, max) {
  return Number.isSafeInteger(value) && value > 0 && value <= max;
}

/**
 * Validate a canonical frame without mutating it.
 *
 * Frame shape:
 * {
 *   version: 1, topologyId: string, timestampMs: number,
 *   sourceWidth: integer, sourceHeight: integer,
 *   faces: [{ confidence?: number, landmarks: [{ x: number, y: number, z: number }] }]
 * }
 */
export function validateLandmarkFrame(frame, options = {}) {
  const limits = { ...DEFAULT_LIMITS, ...options };
  if (!frame || typeof frame !== "object" || Array.isArray(frame)) {
    return failure("frame-not-object");
  }
  if (frame.version !== LANDMARK_FRAME_VERSION) return failure("unsupported-version");
  if (typeof frame.topologyId !== "string" || frame.topologyId.trim() === "") {
    return failure("missing-topology");
  }
  if (options.expectedTopologyId && frame.topologyId !== options.expectedTopologyId) {
    return failure("topology-mismatch");
  }
  if (!Number.isFinite(frame.timestampMs) || frame.timestampMs < 0) {
    return failure("invalid-timestamp");
  }
  if (!isPositiveInteger(frame.sourceWidth, limits.maxDimension)
      || !isPositiveInteger(frame.sourceHeight, limits.maxDimension)) {
    return failure("invalid-source-dimensions");
  }
  if (!Array.isArray(frame.faces) || frame.faces.length > limits.maxFaces) {
    return failure("invalid-face-count");
  }

  for (const face of frame.faces) {
    if (!face || typeof face !== "object" || Array.isArray(face)) {
      return failure("invalid-face");
    }
    if (face.confidence !== undefined
        && (!Number.isFinite(face.confidence) || face.confidence < 0 || face.confidence > 1)) {
      return failure("invalid-confidence");
    }
    if (!Array.isArray(face.landmarks)
        || face.landmarks.length < limits.minLandmarks
        || face.landmarks.length > limits.maxLandmarks) {
      return failure("invalid-landmark-count");
    }
    for (const point of face.landmarks) {
      if (!point || typeof point !== "object"
          || !Number.isFinite(point.x) || point.x < 0 || point.x > 1
          || !Number.isFinite(point.y) || point.y < 0 || point.y > 1
          || !Number.isFinite(point.z)) {
        return failure("invalid-landmark-coordinate");
      }
    }
  }

  return Object.freeze({ ok: true, frame });
}

/**
 * Stateful guard for live streams. Rejects duplicate/out-of-order timestamps
 * and lets callers reset it when the media source changes.
 */
export function createLandmarkFrameValidator(options = {}) {
  let lastTimestampMs = -1;

  return Object.freeze({
    validate(frame) {
      const result = validateLandmarkFrame(frame, options);
      if (!result.ok) return result;
      if (frame.timestampMs <= lastTimestampMs) return failure("stale-timestamp");
      lastTimestampMs = frame.timestampMs;
      return result;
    },
    reset() {
      lastTimestampMs = -1;
    },
  });
}
