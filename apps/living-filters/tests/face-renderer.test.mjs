import test from "node:test";
import assert from "node:assert/strict";
import {
  FACE_TOPOLOGY_ID,
  drawTrackedAccessory,
  drawTrackedMakeup,
  hasRenderableFace,
  makeHairTintPixels,
} from "../src/face-renderer.mjs";

function mockFace() {
  const landmarks = Array.from({ length: 478 }, (_, index) => ({
    x: 0.25 + ((index % 15) / 100),
    y: 0.25 + ((index % 23) / 100),
    z: 0,
  }));
  const set = (i, x, y) => { landmarks[i] = { x, y, z: 0 }; };
  set(33, 0.35, 0.4); set(133, 0.43, 0.4);
  set(362, 0.57, 0.4); set(263, 0.65, 0.4);
  set(234, 0.22, 0.57); set(454, 0.78, 0.57);
  set(61, 0.42, 0.62); set(291, 0.58, 0.62);
  set(146, 0.43, 0.63); set(91, 0.45, 0.64); set(181, 0.47, 0.65);
  set(84, 0.49, 0.65); set(17, 0.5, 0.65); set(314, 0.51, 0.65);
  set(405, 0.53, 0.65); set(321, 0.55, 0.64); set(375, 0.57, 0.63);
  set(409, 0.56, 0.64); set(270, 0.54, 0.64); set(269, 0.52, 0.64);
  set(267, 0.5, 0.64); set(0, 0.48, 0.64); set(37, 0.46, 0.64);
  set(39, 0.44, 0.64); set(40, 0.43, 0.64); set(185, 0.42, 0.64);
  set(78, 0.43, 0.63); set(191, 0.44, 0.635); set(80, 0.45, 0.635);
  set(81, 0.46, 0.635); set(82, 0.47, 0.635); set(13, 0.5, 0.635);
  set(312, 0.53, 0.635); set(311, 0.54, 0.635); set(310, 0.55, 0.635);
  set(415, 0.56, 0.635); set(308, 0.57, 0.635); set(324, 0.56, 0.64);
  set(318, 0.54, 0.64); set(402, 0.52, 0.64); set(317, 0.5, 0.64);
  set(14, 0.48, 0.64); set(87, 0.46, 0.64); set(178, 0.45, 0.64);
  set(88, 0.44, 0.64); set(95, 0.43, 0.64);
  return landmarks;
}

function mockContext() {
  const calls = [];
  const gradient = { addColorStop() {} };
  return {
    calls,
    save() { calls.push("save"); },
    restore() { calls.push("restore"); },
    beginPath() { calls.push("beginPath"); },
    moveTo() { calls.push("moveTo"); },
    lineTo() { calls.push("lineTo"); },
    quadraticCurveTo() { calls.push("quadraticCurveTo"); },
    closePath() { calls.push("closePath"); },
    fill(rule) { calls.push(["fill", rule]); },
    stroke() { calls.push("stroke"); },
    ellipse() { calls.push("ellipse"); },
    arc() { calls.push("arc"); },
    translate() {},
    scale() {},
    createRadialGradient() { return gradient; },
    set fillStyle(value) {},
    set strokeStyle(value) {},
    set lineWidth(value) {},
    set lineCap(value) {},
    set lineJoin(value) {},
    set shadowColor(value) {},
    set shadowBlur(value) {},
  };
}

test("renderer requires the expected face topology and a sufficiently complete face", () => {
  assert.equal(FACE_TOPOLOGY_ID, "mediapipe-face-landmarker-v1-478");
  assert.equal(hasRenderableFace(mockFace()), true);
  assert.equal(hasRenderableFace(mockFace().slice(0, 400)), false);
  const invalid = mockFace();
  invalid[33] = { x: 1.4, y: 0.4, z: 0 };
  assert.equal(hasRenderableFace(invalid), false);
});

test("lipstick tracks the mouth and natural/full makeup render without throwing", () => {
  const landmarks = mockFace();
  const naturalContext = mockContext();
  assert.equal(drawTrackedMakeup(naturalContext, landmarks, 640, 480, "natural"), true);
  assert.ok(naturalContext.calls.some((call) => Array.isArray(call) && call[0] === "fill" && call[1] === "evenodd"));
  const fullContext = mockContext();
  assert.equal(drawTrackedMakeup(fullContext, landmarks, 640, 480, "full"), true);
  assert.ok(fullContext.calls.filter((call) => call === "ellipse").length >= 2);
});

test("face-tracked glasses and earrings use landmark anchors", () => {
  const glassesContext = mockContext();
  assert.equal(drawTrackedAccessory(glassesContext, mockFace(), 640, 480, "glasses"), true);
  assert.ok(glassesContext.calls.includes("ellipse"));
  const earringsContext = mockContext();
  assert.equal(drawTrackedAccessory(earringsContext, mockFace(), 640, 480, "earrings"), true);
  assert.equal(earringsContext.calls.filter((call) => call === "arc").length, 2);
  const headbandContext = mockContext();
  assert.equal(drawTrackedAccessory(headbandContext, mockFace(), 640, 480, "headband"), true);
  assert.ok(headbandContext.calls.includes("quadraticCurveTo"));
  assert.equal(drawTrackedAccessory(mockContext(), mockFace(), 640, 480, "unknown"), false);
});

test("hair category mask recolours only the hair class and leaves original pixels transparent", () => {
  const data = makeHairTintPixels(new Uint8Array([0, 1, 1, 0]), 2, 2, "#c050a0", 120);
  assert.deepEqual([...data.slice(0, 4)], [0, 0, 0, 0]);
  assert.deepEqual([...data.slice(4, 8)], [192, 80, 160, 120]);
  assert.deepEqual([...data.slice(8, 12)], [192, 80, 160, 120]);
  assert.deepEqual([...data.slice(12, 16)], [0, 0, 0, 0]);
});

test("hair mask dimensions and colour inputs are validated", () => {
  assert.throws(() => makeHairTintPixels(new Uint8Array([1]), 2, 2), /Invalid hair category mask/);
  assert.throws(() => makeHairTintPixels(new Uint8Array([1]), 1, 1, "red"), /six-digit hex/);
  assert.throws(() => makeHairTintPixels(new Uint8Array([1]), 1, 1, "#ffffff", 256), /alpha/);
});
