import { FilesetResolver, FaceLandmarker, ImageSegmenter } from "../vendor/mediapipe/vision_bundle.mjs";
import { validateLandmarkFrame } from "./landmark-frame-contract.mjs";
import { FACE_TOPOLOGY_ID } from "./face-renderer.mjs";

let faceLandmarker = null;
let hairSegmenter = null;
let busy = false;
let disposed = false;
let lastTimestamp = -1;
let sessionToken = 0;

const wasmRoot = new URL("../vendor/mediapipe/wasm/", import.meta.url).href;
const faceModelPath = new URL("../models/face_landmarker.task", import.meta.url).href;
const hairModelPath = new URL("../models/hair_segmenter.tflite", import.meta.url).href;

async function initialise() {
  disposed = false;
  const vision = await FilesetResolver.forVisionTasks(wasmRoot);
  faceLandmarker = await FaceLandmarker.createFromOptions(vision, {
    baseOptions: { modelAssetPath: faceModelPath, delegate: "CPU" },
    runningMode: "VIDEO",
    numFaces: 1,
    minFaceDetectionConfidence: 0.55,
    minFacePresenceConfidence: 0.55,
    minTrackingConfidence: 0.55,
    outputFaceBlendshapes: false,
    outputFacialTransformationMatrixes: false,
  });
  hairSegmenter = await ImageSegmenter.createFromOptions(vision, {
    baseOptions: { modelAssetPath: hairModelPath, delegate: "CPU" },
    runningMode: "VIDEO",
    outputCategoryMask: true,
    outputConfidenceMasks: false,
  });
  lastTimestamp = -1;
  self.postMessage({ type: "ready", session: sessionToken });
}

function makeCanonicalFrame(result, timestamp, sourceWidth, sourceHeight) {
  const detectedFaces = result?.faceLandmarks ?? [];
  const landmarks = detectedFaces[0];
  const faces = Array.isArray(landmarks) && landmarks.length === 478
    ? [{ landmarks: landmarks.map(({ x, y, z }) => ({ x, y, z })) }]
    : [];
  const candidate = {
    version: 1,
    topologyId: FACE_TOPOLOGY_ID,
    timestampMs: timestamp,
    sourceWidth,
    sourceHeight,
    faces,
  };
  const validated = validateLandmarkFrame(candidate, { expectedTopologyId: FACE_TOPOLOGY_ID });
  if (!validated.ok) throw new Error("Invalid landmark frame: " + validated.reason);
  return candidate;
}

function getHairMask(frame, timestamp) {
  const result = hairSegmenter.segmentForVideo(frame, timestamp);
  try {
    const mask = result?.categoryMask;
    if (!mask || !Number.isSafeInteger(mask.width) || !Number.isSafeInteger(mask.height)) return null;
    const labels = hairSegmenter.getLabels().map((label) => String(label).trim().toLowerCase());
    const discoveredHairClass = labels.findIndex((label) => label === "hair" || label.includes("hair"));
    // The pinned HairSegmenter v1 model card specifies 0=background, 1=hair.
    // Use this documented fallback only when model metadata has no label map;
    // never guess when a supplied label map contradicts the expected class.
    const hairClass = labels.length === 0 ? 1 : discoveredHairClass;
    if (hairClass < 0) throw new Error("The pinned segmentation model does not declare a hair class.");
    // The MediaPipe mask buffer is only guaranteed during result lifetime; clone
    // and normalize the model's label index to a binary hair mask before closing.
    const source = mask.getAsUint8Array();
    const binary = new Uint8Array(source.length);
    for (let index = 0; index < source.length; index += 1) {
      binary[index] = source[index] === hairClass ? 1 : 0;
    }
    return { width: mask.width, height: mask.height, data: binary.buffer };
  } finally {
    result?.close?.();
  }
}

async function processFrame(message) {
  const { bitmap, timestamp, session, needHair } = message;
  if (!(bitmap instanceof ImageBitmap)) {
    self.postMessage({ type: "error", session, message: "A frame could not be transferred to the vision worker." });
    return;
  }
  if (session !== sessionToken || busy || !faceLandmarker || disposed) {
    bitmap.close();
    return;
  }
  if (!Number.isFinite(timestamp) || timestamp <= lastTimestamp) {
    bitmap.close();
    self.postMessage({ type: "error", session, message: "A stale frame was discarded." });
    return;
  }

  busy = true;
  lastTimestamp = timestamp;
  try {
    const faceResult = faceLandmarker.detectForVideo(bitmap, timestamp);
    const faceFrame = makeCanonicalFrame(faceResult, timestamp, bitmap.width, bitmap.height);
    let hairMask = null;
    if (needHair && hairSegmenter) hairMask = getHairMask(bitmap, timestamp);
    const transfers = hairMask ? [hairMask.data] : [];
    self.postMessage({
      type: "frame-result",
      session,
      frame: faceFrame,
      hairMask,
    }, transfers);
  } catch (error) {
    self.postMessage({
      type: "error",
      session,
      message: error?.message || "Local vision processing failed.",
    });
  } finally {
    bitmap.close();
    busy = false;
  }
}

function dispose() {
  disposed = true;
  try { faceLandmarker?.close?.(); } catch {}
  try { hairSegmenter?.close?.(); } catch {}
  faceLandmarker = null;
  hairSegmenter = null;
  busy = false;
  lastTimestamp = -1;
}

self.addEventListener("message", async (event) => {
  const message = event.data;
  if (!message || typeof message.type !== "string") return;
  if (message.type === "init") {
    try {
      dispose();
      sessionToken = message.session;
      await initialise();
    } catch (error) {
      dispose();
      self.postMessage({
        type: "init-error",
        session: message.session,
        message: error?.message || "Local vision assets could not be initialized.",
      });
    }
  } else if (message.type === "frame") {
    await processFrame(message);
  } else if (message.type === "dispose") {
    sessionToken = message.session;
    dispose();
    self.postMessage({ type: "disposed", session: message.session });
  }
});
