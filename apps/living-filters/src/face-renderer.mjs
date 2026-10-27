/**
 * Cosmetic/accessory rendering helpers for the MediaPipe Face Landmarker topology.
 * Rendering is local-only and decorative; no function estimates skin health or fit.
 */
export const FACE_TOPOLOGY_ID = "mediapipe-face-landmarker-v1-478";

export const LANDMARKS = Object.freeze({
  leftEyeOuter: 33,
  leftEyeInner: 133,
  rightEyeInner: 362,
  rightEyeOuter: 263,
  leftCheekEdge: 234,
  rightCheekEdge: 454,
  leftLipCorner: 61,
  rightLipCorner: 291,
});

const LIP_OUTER = Object.freeze([61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]);
const LIP_INNER = Object.freeze([78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95]);
const LEFT_EYE_SHADOW = Object.freeze([33, 160, 159, 158, 157, 173, 133, 246]);
const RIGHT_EYE_SHADOW = Object.freeze([362, 385, 386, 387, 388, 466, 263, 359]);

function point(landmarks, index, width, height) {
  const item = landmarks?.[index];
  if (!item || !Number.isFinite(item.x) || !Number.isFinite(item.y)) return null;
  if (item.x < 0 || item.x > 1 || item.y < 0 || item.y > 1) return null;
  return { x: item.x * width, y: item.y * height };
}

function distance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function pathFromIndices(context, landmarks, indices, width, height) {
  const points = indices.map((index) => point(landmarks, index, width, height));
  if (points.some((item) => item === null)) return false;
  context.moveTo(points[0].x, points[0].y);
  for (let index = 1; index < points.length; index += 1) {
    context.lineTo(points[index].x, points[index].y);
  }
  context.closePath();
  return true;
}

export function hasRenderableFace(landmarks) {
  if (!Array.isArray(landmarks) || landmarks.length < 455) return false;
  const required = [
    LANDMARKS.leftEyeOuter, LANDMARKS.leftEyeInner,
    LANDMARKS.rightEyeInner, LANDMARKS.rightEyeOuter,
    LANDMARKS.leftCheekEdge, LANDMARKS.rightCheekEdge,
    LANDMARKS.leftLipCorner, LANDMARKS.rightLipCorner,
  ];
  return required.every((index) => {
    const item = landmarks[index];
    return item && Number.isFinite(item.x) && Number.isFinite(item.y)
      && item.x >= 0 && item.x <= 1 && item.y >= 0 && item.y <= 1;
  });
}

function drawLipstick(context, landmarks, width, height, color) {
  context.save();
  context.fillStyle = color;
  context.shadowColor = color;
  context.shadowBlur = Math.max(1, width * 0.0015);
  context.beginPath();
  const outer = pathFromIndices(context, landmarks, LIP_OUTER, width, height);
  const inner = pathFromIndices(context, landmarks, LIP_INNER, width, height);
  if (outer && inner) context.fill("evenodd");
  context.restore();
}

function drawEyeShadow(context, landmarks, width, height, ids) {
  const outer = point(landmarks, ids[0], width, height);
  const inner = point(landmarks, ids[1], width, height);
  if (!outer || !inner) return;
  const eyeWidth = distance(outer, inner);
  if (eyeWidth < 2) return;
  const angle = Math.atan2(inner.y - outer.y, inner.x - outer.x);
  const centerX = (outer.x + inner.x) / 2;
  const centerY = (outer.y + inner.y) / 2 - eyeWidth * 0.22;
  const gradient = context.createRadialGradient(centerX, centerY, eyeWidth * 0.04, centerX, centerY, eyeWidth * 0.72);
  gradient.addColorStop(0, "rgba(177, 94, 145, 0.46)");
  gradient.addColorStop(0.65, "rgba(137, 77, 132, 0.22)");
  gradient.addColorStop(1, "rgba(137, 77, 132, 0)");
  context.save();
  context.fillStyle = gradient;
  context.beginPath();
  context.ellipse(centerX, centerY, eyeWidth * 0.66, eyeWidth * 0.32, angle, 0, Math.PI * 2);
  context.fill();
  context.restore();
}

function drawBlush(context, landmarks, width, height, cheekIndex, lipIndex, flip) {
  const cheek = point(landmarks, cheekIndex, width, height);
  const lip = point(landmarks, lipIndex, width, height);
  if (!cheek || !lip) return;
  const faceSpan = Math.abs(
    (point(landmarks, LANDMARKS.rightCheekEdge, width, height)?.x ?? width * 0.7)
    - (point(landmarks, LANDMARKS.leftCheekEdge, width, height)?.x ?? width * 0.3),
  );
  const cx = cheek.x * 0.46 + lip.x * 0.54;
  const cy = cheek.y * 0.34 + lip.y * 0.66 - faceSpan * 0.012;
  const radius = Math.max(3, faceSpan * 0.09);
  const gradient = context.createRadialGradient(cx, cy, radius * 0.05, cx, cy, radius);
  gradient.addColorStop(0, "rgba(231, 95, 132, 0.32)");
  gradient.addColorStop(0.6, "rgba(231, 95, 132, 0.15)");
  gradient.addColorStop(1, "rgba(231, 95, 132, 0)");
  context.save();
  context.translate(cx, cy);
  context.scale(1.32, 0.68);
  context.fillStyle = gradient;
  context.beginPath();
  context.arc(0, 0, radius, 0, Math.PI * 2);
  context.fill();
  context.restore();
}

export function drawTrackedMakeup(context, landmarks, width, height, style = "natural") {
  if (!context || !hasRenderableFace(landmarks) || width <= 0 || height <= 0) return false;
  const lipstick = style === "berry"
    ? "rgba(150, 20, 66, 0.72)"
    : "rgba(202, 66, 101, 0.55)";

  if (style === "full") {
    drawEyeShadow(context, landmarks, width, height, [LANDMARKS.leftEyeOuter, LANDMARKS.leftEyeInner]);
    drawEyeShadow(context, landmarks, width, height, [LANDMARKS.rightEyeOuter, LANDMARKS.rightEyeInner]);
    drawBlush(context, landmarks, width, height, LANDMARKS.leftCheekEdge, LANDMARKS.leftLipCorner, false);
    drawBlush(context, landmarks, width, height, LANDMARKS.rightCheekEdge, LANDMARKS.rightLipCorner, true);
  }
  drawLipstick(context, landmarks, width, height, lipstick);
  return true;
}

export function drawTrackedAccessory(context, landmarks, width, height, kind = "glasses") {
  if (!context || !hasRenderableFace(landmarks) || width <= 0 || height <= 0) return false;
  const leftOuter = point(landmarks, LANDMARKS.leftEyeOuter, width, height);
  const leftInner = point(landmarks, LANDMARKS.leftEyeInner, width, height);
  const rightInner = point(landmarks, LANDMARKS.rightEyeInner, width, height);
  const rightOuter = point(landmarks, LANDMARKS.rightEyeOuter, width, height);
  if (![leftOuter, leftInner, rightInner, rightOuter].every(Boolean)) return false;

  context.save();
  context.strokeStyle = kind === "glasses" ? "rgba(38, 28, 43, 0.9)" : "rgba(221, 174, 92, 0.95)";
  context.fillStyle = "rgba(255, 244, 250, 0.08)";
  context.lineWidth = Math.max(1.5, Math.abs(rightOuter.x - leftOuter.x) * 0.008);
  context.lineCap = "round";
  context.lineJoin = "round";

  if (kind === "glasses") {
    const eyeLeftWidth = distance(leftOuter, leftInner);
    const eyeRightWidth = distance(rightInner, rightOuter);
    const leftCenter = { x: (leftOuter.x + leftInner.x) / 2, y: (leftOuter.y + leftInner.y) / 2 };
    const rightCenter = { x: (rightInner.x + rightOuter.x) / 2, y: (rightInner.y + rightOuter.y) / 2 };
    context.beginPath();
    context.ellipse(leftCenter.x, leftCenter.y, eyeLeftWidth * 0.66, eyeLeftWidth * 0.4, Math.atan2(leftInner.y - leftOuter.y, leftInner.x - leftOuter.x), 0, Math.PI * 2);
    context.ellipse(rightCenter.x, rightCenter.y, eyeRightWidth * 0.66, eyeRightWidth * 0.4, Math.atan2(rightOuter.y - rightInner.y, rightOuter.x - rightInner.x), 0, Math.PI * 2);
    context.fill();
    context.stroke();
    context.beginPath();
    context.moveTo(leftInner.x, leftInner.y);
    context.lineTo(rightInner.x, rightInner.y);
    context.moveTo(leftOuter.x - eyeLeftWidth * 0.42, leftOuter.y);
    context.lineTo(leftOuter.x, leftOuter.y);
    context.moveTo(rightOuter.x, rightOuter.y);
    context.lineTo(rightOuter.x + eyeRightWidth * 0.42, rightOuter.y);
    context.stroke();
  } else if (kind === "earrings") {
    for (const index of [LANDMARKS.leftCheekEdge, LANDMARKS.rightCheekEdge]) {
      const anchor = point(landmarks, index, width, height);
      if (!anchor) continue;
      const leftSide = index === LANDMARKS.leftCheekEdge;
      const eyeWidth = distance(leftOuter, leftInner);
      const cx = anchor.x + (leftSide ? -1 : 1) * eyeWidth * 0.035;
      const cy = anchor.y + eyeWidth * 0.21;
      const radius = Math.max(2.5, eyeWidth * 0.11);
      context.beginPath();
      context.arc(cx, cy, radius, 0, Math.PI * 2);
      context.stroke();
      context.beginPath();
      context.moveTo(cx, cy + radius);
      context.lineTo(cx, cy + radius * 1.7);
      context.stroke();
    }
  } else if (kind === "headband") {
    const leftTemple = point(landmarks, 109, width, height);
    const forehead = point(landmarks, 10, width, height);
    const rightTemple = point(landmarks, 338, width, height);
    if (!leftTemple || !forehead || !rightTemple) {
      context.restore();
      return false;
    }
    const span = distance(leftTemple, rightTemple);
    if (span < 8) {
      context.restore();
      return false;
    }
    // Two landmark-anchored curves form a small decorative headband.
    context.strokeStyle = "rgba(209, 167, 91, 0.96)";
    context.lineWidth = Math.max(2, span * 0.035);
    context.beginPath();
    context.moveTo(leftTemple.x, leftTemple.y);
    context.quadraticCurveTo(forehead.x, forehead.y - span * 0.045, rightTemple.x, rightTemple.y);
    context.stroke();
    context.strokeStyle = "rgba(255, 229, 179, 0.95)";
    context.lineWidth = Math.max(1, span * 0.012);
    context.beginPath();
    context.moveTo(leftTemple.x, leftTemple.y + span * 0.018);
    context.quadraticCurveTo(forehead.x, forehead.y - span * 0.015, rightTemple.x, rightTemple.y + span * 0.018);
    context.stroke();
    context.fillStyle = "rgba(255, 239, 191, 0.98)";
    context.beginPath();
    context.arc(forehead.x, forehead.y - span * 0.045, Math.max(2, span * 0.018), 0, Math.PI * 2);
    context.fill();
  } else {
    context.restore();
    return false;
  }
  context.restore();
  return true;
}

/** Build a transparent coloured overlay from a category mask (hair class = 1). */
export function makeHairTintPixels(maskData, width, height, color = "#b65f35", alpha = 148) {
  if (!ArrayBuffer.isView(maskData) || !Number.isSafeInteger(width) || !Number.isSafeInteger(height)
      || width <= 0 || height <= 0 || width * height !== maskData.length) {
    throw new TypeError("Invalid hair category mask dimensions or data.");
  }
  if (!/^#[0-9a-f]{6}$/i.test(color)) throw new TypeError("Hair tint colour must be a six-digit hex colour.");
  if (!Number.isFinite(alpha) || alpha < 0 || alpha > 255) throw new RangeError("Hair tint alpha must be in [0,255].");
  const red = Number.parseInt(color.slice(1, 3), 16);
  const green = Number.parseInt(color.slice(3, 5), 16);
  const blue = Number.parseInt(color.slice(5, 7), 16);
  const pixels = new Uint8ClampedArray(maskData.length * 4);
  for (let index = 0; index < maskData.length; index += 1) {
    if (maskData[index] !== 1) continue;
    const offset = index * 4;
    pixels[offset] = red;
    pixels[offset + 1] = green;
    pixels[offset + 2] = blue;
    pixels[offset + 3] = alpha;
  }
  return pixels;
}
