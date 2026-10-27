import { FILTERS, getFilterById } from "./filter-catalog.mjs";
import { createRequestEpoch } from "./request-epoch.mjs";
import { drawTrackedAccessory, drawTrackedMakeup, makeHairTintPixels } from "./face-renderer.mjs";

const elements = {
  stage: document.querySelector("#stage"),
  overlayCanvas: document.querySelector("#ar-overlay"),
  video: document.querySelector("#camera-preview"),
  image: document.querySelector("#photo-preview"),
  empty: document.querySelector("#stage-empty"),
  label: document.querySelector("#stage-label"),
  file: document.querySelector("#photo-input"),
  startCamera: document.querySelector("#start-camera"),
  stopCamera: document.querySelector("#stop-camera"),
  capture: document.querySelector("#capture"),
  status: document.querySelector("#status"),
  filterGrid: document.querySelector("#filter-grid"),
  filterCount: document.querySelector("#filter-count"),
  selectedName: document.querySelector("#selected-name"),
  selectedDescription: document.querySelector("#selected-description"),
  arConsent: document.querySelector("#ar-consent"),
  arStart: document.querySelector("#ar-start"),
  arStop: document.querySelector("#ar-stop"),
  arModeGrid: document.querySelector("#ar-mode-grid"),
  arStatus: document.querySelector("#ar-status"),
};

const cameraRequestEpoch = createRequestEpoch();
const visionState = {
  worker: null,
  session: 0,
  loading: false,
  ready: false,
  mode: "off",
  latestLandmarks: null,
  hairMask: null,
  frameInFlight: false,
  lastFrameSentAt: -Infinity,
  lastTimestamp: -1,
  rafId: null,
  hairCanvas: null,
  photoHairRetryCount: 0,
};

let cameraStream = null;
let uploadedObjectUrl = null;
let activeSource = null;
let activeFilter = getFilterById("original");

function setStatus(message) {
  elements.status.textContent = message;
}

function setARStatus(message) {
  elements.arStatus.textContent = message;
}

function currentSourceElement() {
  if (activeSource === "camera") return elements.video;
  if (activeSource === "photo") return elements.image;
  return null;
}

function updateARControls() {
  elements.arStart.disabled = !elements.arConsent.checked
    || !isSourceReady() || Boolean(visionState.worker) || visionState.loading;
  elements.arStop.disabled = !visionState.worker && !visionState.loading;
  for (const button of elements.arModeGrid.querySelectorAll("button[data-ar-mode]")) {
    button.disabled = !visionState.ready;
    button.setAttribute("aria-pressed", String(button.dataset.arMode === visionState.mode));
  }
}

function clearARCanvas() {
  const context = elements.overlayCanvas.getContext("2d");
  if (context) context.clearRect(0, 0, elements.overlayCanvas.width, elements.overlayCanvas.height);
  elements.overlayCanvas.hidden = true;
}

function stopVision(message = "On-device face tracking is stopped.", showStatus = true) {
  visionState.session += 1;
  if (visionState.rafId !== null) cancelAnimationFrame(visionState.rafId);
  visionState.rafId = null;
  if (visionState.worker) {
    try { visionState.worker.postMessage({ type: "dispose", session: visionState.session }); } catch {}
    visionState.worker.terminate();
  }
  visionState.worker = null;
  visionState.loading = false;
  visionState.ready = false;
  visionState.mode = "off";
  visionState.latestLandmarks = null;
  visionState.hairMask = null;
  visionState.frameInFlight = false;
  visionState.lastFrameSentAt = -Infinity;
  visionState.lastTimestamp = -1;
  clearARCanvas();
  updateARControls();
  if (showStatus) setARStatus(message);
}

function drawHairOverlay(context, width, height, mask, color) {
  if (!mask || !mask.data || !mask.width || !mask.height) return false;
  const data = mask.data instanceof Uint8Array ? mask.data : new Uint8Array(mask.data);
  const pixels = makeHairTintPixels(data, mask.width, mask.height, color, 150);
  if (!visionState.hairCanvas) visionState.hairCanvas = document.createElement("canvas");
  const canvas = visionState.hairCanvas;
  if (canvas.width !== mask.width) canvas.width = mask.width;
  if (canvas.height !== mask.height) canvas.height = mask.height;
  const maskContext = canvas.getContext("2d");
  if (!maskContext) return false;
  maskContext.putImageData(new ImageData(pixels, mask.width, mask.height), 0, 0);
  context.save();
  context.globalAlpha = 0.76;
  context.filter = "blur(0.65px)";
  context.drawImage(canvas, 0, 0, width, height);
  context.restore();
  return true;
}

function drawARToContext(context, width, height) {
  const landmarks = visionState.latestLandmarks;
  if (visionState.mode === "hair-copper") {
    drawHairOverlay(context, width, height, visionState.hairMask, "#b65f35");
  } else if (visionState.mode === "hair-violet") {
    drawHairOverlay(context, width, height, visionState.hairMask, "#8650b8");
  } else if (visionState.mode === "lipstick" && landmarks) {
    drawTrackedMakeup(context, landmarks, width, height, "berry");
  } else if (visionState.mode === "makeup" && landmarks) {
    drawTrackedMakeup(context, landmarks, width, height, "full");
  } else if (visionState.mode === "glasses" && landmarks) {
    drawTrackedAccessory(context, landmarks, width, height, "glasses");
  } else if (visionState.mode === "earrings" && landmarks) {
    drawTrackedAccessory(context, landmarks, width, height, "earrings");
  } else if (visionState.mode === "headband" && landmarks) {
    drawTrackedAccessory(context, landmarks, width, height, "headband");
  }
}

function renderAROverlay() {
  const [width, height] = getSourceDimensions();
  if (!visionState.ready || visionState.mode === "off" || !width || !height) {
    clearARCanvas();
    return;
  }
  if (elements.overlayCanvas.width !== width) elements.overlayCanvas.width = width;
  if (elements.overlayCanvas.height !== height) elements.overlayCanvas.height = height;
  const context = elements.overlayCanvas.getContext("2d");
  if (!context) {
    clearARCanvas();
    return;
  }
  context.clearRect(0, 0, width, height);
  drawARToContext(context, width, height);
  elements.overlayCanvas.hidden = false;
}

function queueVisionFrame() {
  if (!visionState.worker || !visionState.ready || visionState.frameInFlight || !isSourceReady()) return;
  const now = performance.now();
  const hairMode = visionState.mode === "hair-copper" || visionState.mode === "hair-violet";
  const minimumInterval = hairMode ? 230 : 90;
  if (activeSource === "camera" && now - visionState.lastFrameSentAt < minimumInterval) return;

  const source = currentSourceElement();
  if (!source) return;
  const session = visionState.session;
  const timestamp = Math.max(Math.floor(now), visionState.lastTimestamp + 1);
  visionState.lastTimestamp = timestamp;
  visionState.lastFrameSentAt = now;
  visionState.frameInFlight = true;

  createImageBitmap(source).then((bitmap) => {
    if (session !== visionState.session || !visionState.worker || !visionState.ready) {
      bitmap.close();
      visionState.frameInFlight = false;
      return;
    }
    visionState.worker.postMessage({
      type: "frame",
      session,
      timestamp,
      needHair: hairMode,
      bitmap,
    }, [bitmap]);
  }).catch(() => {
    if (session !== visionState.session) return;
    visionState.frameInFlight = false;
    setARStatus("This browser could not create a local video frame. Stop try-on or use the photo preview.");
  });
}

function startVisionLoop() {
  if (visionState.rafId !== null) cancelAnimationFrame(visionState.rafId);
  const tick = () => {
    if (!visionState.worker || !visionState.ready) {
      visionState.rafId = null;
      return;
    }
    if (activeSource === "camera") queueVisionFrame();
    visionState.rafId = requestAnimationFrame(tick);
  };
  visionState.rafId = requestAnimationFrame(tick);
}

function startVision() {
  if (!elements.arConsent.checked) {
    setARStatus("Please opt in to local face/hair landmark processing before starting.");
    return;
  }
  if (!isSourceReady()) {
    setARStatus("Choose a photo or start the camera before enabling face-tracked effects.");
    return;
  }
  if (visionState.worker || visionState.loading) return;

  visionState.session += 1;
  const session = visionState.session;
  visionState.loading = true;
  visionState.mode = "off";
  visionState.latestLandmarks = null;
  visionState.hairMask = null;
  visionState.frameInFlight = false;
  visionState.lastTimestamp = -1;
  visionState.photoHairRetryCount = 0;
  updateARControls();
  setARStatus("Loading pinned local vision runtime and model files… no CDN fallback is used.");

  let worker;
  try {
    worker = new Worker(new URL("./vision-worker.mjs", import.meta.url), {
      type: "module",
      name: "cirvanna-living-filters-vision",
    });
  } catch {
    visionState.loading = false;
    updateARControls();
    setARStatus("This browser could not start the local vision worker. Existing colour filters still work.");
    return;
  }
  visionState.worker = worker;
  worker.onmessage = (event) => {
    const data = event.data;
    if (session !== visionState.session || (data?.session !== undefined && data.session !== session)) return;
    if (data?.type === "ready") {
      visionState.loading = false;
      visionState.ready = true;
      updateARControls();
      setARStatus("Local face and hair models are ready. Choose a makeup, hair-colour, or accessory effect.");
      if (activeSource === "camera") startVisionLoop();
      else queueVisionFrame();
    } else if (data?.type === "frame-result") {
      visionState.frameInFlight = false;
      visionState.latestLandmarks = data.frame?.faces?.[0]?.landmarks ?? null;
      if (data.hairMask) visionState.hairMask = {
        width: data.hairMask.width,
        height: data.hairMask.height,
        data: new Uint8Array(data.hairMask.data),
      };
      renderAROverlay();
      const hairModeActive = visionState.mode === "hair-copper" || visionState.mode === "hair-violet";
      if (!visionState.latestLandmarks && visionState.mode !== "off") {
        setARStatus("No clear face was detected. Face-anchored effects are hidden; adjust lighting or face the camera.");
      } else if (activeSource === "photo" && visionState.mode !== "off") {
        if (hairModeActive && !visionState.hairMask) {
          if (visionState.photoHairRetryCount < 1) {
            visionState.photoHairRetryCount += 1;
            setARStatus("Refreshing the local hair mask…");
            queueVisionFrame();
          } else {
            setARStatus("Face landmarks are ready, but a usable hair mask was not returned. No hair recolour is shown.");
          }
        } else {
          setARStatus("Local try-on preview updated. The effect is approximate and is not a skin or fit assessment.");
        }
      }
    } else if (data?.type === "error") {
      visionState.frameInFlight = false;
      // Never leave a previous face/hair overlay on screen after an invalid inference.
      visionState.latestLandmarks = null;
      visionState.hairMask = null;
      renderAROverlay();
      if (data.message !== "A stale frame was discarded.") {
        setARStatus("Local vision skipped a frame. The tracked overlay was cleared; keep the face visible and try again.");
      }
    } else if (data?.type === "init-error") {
      stopVision("Local vision assets are missing, corrupt, or unsupported. Run the pinned asset preparation script on a network-enabled build machine, then reload.", false);
      setARStatus("Could not load the local models. No remote fallback was attempted. Run node apps/living-filters/scripts/prepare-vision-assets.mjs and reload.");
    }
  };
  worker.onerror = () => {
    if (session !== visionState.session) return;
    stopVision("The local vision worker failed. Check that the pinned runtime and model assets were prepared successfully.", false);
    setARStatus("The local vision worker failed. Run node apps/living-filters/scripts/prepare-vision-assets.mjs and reload; no network fallback was attempted.");
  };
  worker.postMessage({ type: "init", session });
}

function selectAREffect(mode) {
  if (!visionState.ready) return;
  visionState.mode = mode;
  visionState.photoHairRetryCount = 0;
  if (!mode.startsWith("hair-")) {
    // Keep a previously computed hair mask in memory only for this session; it is never persisted.
  } else if (!visionState.hairMask && activeSource === "photo") {
    queueVisionFrame();
  }
  updateARControls();
  renderAROverlay();
  const descriptions = {
    off: "Tracked effects are cleared. Local landmark processing remains active until you stop it.",
    lipstick: "Berry lipstick is anchored to detected lip landmarks.",
    makeup: "Lip colour, eye colour wash, and cheek tint follow detected face landmarks.",
    "hair-copper": "Copper recolour follows the local hair segmentation mask. Hair-shape replacement is not included.",
    "hair-violet": "Violet recolour follows the local hair segmentation mask. Hair-shape replacement is not included.",
    glasses: "A decorative 2D glasses overlay follows eye-corner landmarks; it is not a real product fit preview.",
    earrings: "Decorative hoop earrings follow approximate face-side anchors; real 3D occlusion is not implemented.",
    headband: "A decorative headband follows forehead and temple landmarks; hair occlusion and 3D fit are not implemented.",
  };
  setARStatus(descriptions[mode] || "Local effect selected.");
  if (activeSource === "photo") queueVisionFrame();
}

function isSourceReady() {
  if (activeSource === "camera") return elements.video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA;
  if (activeSource === "photo") return elements.image.complete && elements.image.naturalWidth > 0;
  return false;
}

function applyFilter(filter) {
  activeFilter = filter;
  elements.stage.dataset.filter = filter.id;
  elements.stage.dataset.effect = filter.effect;
  elements.selectedName.textContent = filter.name;
  elements.selectedDescription.textContent = filter.description;
  for (const button of elements.filterGrid.querySelectorAll("button[data-filter]")) {
    button.setAttribute("aria-pressed", String(button.dataset.filter === filter.id));
  }
}

function renderFilterButtons() {
  const fragment = document.createDocumentFragment();
  for (const filter of FILTERS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "filter-button";
    button.dataset.filter = filter.id;
    button.setAttribute("aria-pressed", String(filter.id === activeFilter.id));
    button.setAttribute("aria-label", filter.name + ": " + filter.description);

    const swatch = document.createElement("span");
    swatch.className = "filter-swatch";
    swatch.setAttribute("aria-hidden", "true");
    const name = document.createElement("span");
    name.className = "filter-name";
    name.textContent = filter.name;
    const category = document.createElement("span");
    category.className = "filter-category";
    category.textContent = filter.category;

    button.append(swatch, name, category);
    button.addEventListener("click", () => applyFilter(getFilterById(button.dataset.filter)));
    fragment.append(button);
  }
  elements.filterGrid.replaceChildren(fragment);
  elements.filterCount.textContent = String(FILTERS.length) + " looks";
}

function showSource(source) {
  activeSource = source;
  elements.video.hidden = source !== "camera";
  elements.image.hidden = source !== "photo";
  elements.empty.hidden = source !== null;
  elements.capture.disabled = source === null || !isSourceReady();
  elements.stopCamera.disabled = source !== "camera";
  elements.label.textContent = source === "camera" ? "LIVE PREVIEW" : source === "photo" ? "LOCAL PHOTO" : "PREVIEW ONLY";
  updateARControls();
}

function stopCamera() {
  stopVision("Source changed or camera stopped. Re-enable local try-on after selecting a source.");
  // Invalidate any unresolved getUserMedia request before releasing current tracks.
  cameraRequestEpoch.invalidate();
  if (cameraStream) {
    for (const track of cameraStream.getTracks()) track.stop();
    cameraStream = null;
  }
  elements.video.pause();
  elements.video.srcObject = null;
  if (activeSource === "camera") {
    showSource(null);
    setStatus("Camera stopped. Choose a photo or start the camera again.");
  }
}

function releaseUploadedPhoto() {
  if (uploadedObjectUrl) {
    URL.revokeObjectURL(uploadedObjectUrl);
    uploadedObjectUrl = null;
  }
  elements.image.removeAttribute("src");
}

async function startCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    setStatus("Camera access is unavailable here. Use HTTPS or localhost, or choose a photo.");
    return;
  }
  stopVision("Camera source is changing. Re-enable local try-on after the camera starts.", false);
  if (cameraStream) stopCamera();
  const requestEpoch = cameraRequestEpoch.begin();
  setStatus("Requesting camera permission…");
  elements.startCamera.disabled = true;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { facingMode: { ideal: "user" }, width: { ideal: 1280 }, height: { ideal: 960 } },
    });
    // A user may choose a photo or leave the page while permission is pending.
    // Never let a late permission result replace the newer user-selected state.
    if (!cameraRequestEpoch.isCurrent(requestEpoch)) {
      for (const track of stream.getTracks()) track.stop();
      return;
    }
    cameraStream = stream;
    elements.video.srcObject = cameraStream;
    await elements.video.play();
    releaseUploadedPhoto();
    showSource("camera");
    elements.capture.disabled = !isSourceReady();
    setStatus("Camera is active. Your video is processed locally and is not uploaded.");
  } catch (error) {
    if (!cameraRequestEpoch.isCurrent(requestEpoch)) return;
    stopCamera();
    const message = error?.name === "NotAllowedError"
      ? "Camera permission was denied. Enable it in browser settings or choose a photo."
      : error?.name === "NotFoundError"
        ? "No compatible camera was found. Choose a photo to continue."
        : "The camera could not start. Check browser permissions and try again, or choose a photo.";
    setStatus(message);
  } finally {
    elements.startCamera.disabled = false;
  }
}

function loadPhoto(file) {
  if (!file) return;
  if (!["image/jpeg", "image/png", "image/webp", "image/avif"].includes(file.type)) {
    setStatus("Choose a JPEG, PNG, WebP, or AVIF image.");
    elements.file.value = "";
    return;
  }
  if (file.size > 12 * 1024 * 1024) {
    setStatus("That image is larger than 12 MB. Choose a smaller image.");
    elements.file.value = "";
    return;
  }

  stopCamera();
  releaseUploadedPhoto();
  uploadedObjectUrl = URL.createObjectURL(file);
  elements.image.onload = () => {
    if (elements.image.naturalWidth * elements.image.naturalHeight > 40000000) {
      releaseUploadedPhoto();
      showSource(null);
      setStatus("This image has too many pixels for a safe preview. Choose a smaller image.");
      return;
    }
    showSource("photo");
    elements.capture.disabled = false;
    updateARControls();
    setStatus("Photo loaded locally. It has not been uploaded or added to an account.");
  };
  elements.image.onerror = () => {
    releaseUploadedPhoto();
    showSource(null);
    setStatus("This image could not be decoded. Try another file.");
  };
  elements.image.src = uploadedObjectUrl;
}

function drawDecorativeOverlay(context, width, height, effect) {
  if (effect === "aurora") {
    const gradient = context.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, "rgba(242,183,210,0.22)");
    gradient.addColorStop(0.48, "rgba(0,0,0,0)");
    gradient.addColorStop(1, "rgba(153,130,213,0.2)");
    context.fillStyle = gradient;
    context.fillRect(0, 0, width, height);
  } else if (effect === "soft-glow") {
    const gradient = context.createRadialGradient(width * 0.5, height * 0.36, 0, width * 0.5, height * 0.36, Math.max(width, height) * 0.6);
    gradient.addColorStop(0, "rgba(255,228,207,0.18)");
    gradient.addColorStop(1, "rgba(255,228,207,0)");
    context.fillStyle = gradient;
    context.fillRect(0, 0, width, height);
  } else if (effect === "rose-haze") {
    const gradient = context.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, "rgba(247,160,193,0.18)");
    gradient.addColorStop(1, "rgba(222,176,208,0.16)");
    context.fillStyle = gradient;
    context.fillRect(0, 0, width, height);
  } else if (effect === "starlight") {
    const points = [[0.18, 0.21], [0.81, 0.17], [0.78, 0.68], [0.23, 0.76], [0.5, 0.12]];
    context.fillStyle = "rgba(255,240,250,0.95)";
    for (const [x, y] of points) {
      context.beginPath();
      context.arc(width * x, height * y, Math.max(1, Math.min(width, height) * 0.0025), 0, Math.PI * 2);
      context.fill();
    }
  }
}

function getSourceDimensions() {
  if (activeSource === "camera") return [elements.video.videoWidth, elements.video.videoHeight];
  if (activeSource === "photo") return [elements.image.naturalWidth, elements.image.naturalHeight];
  return [0, 0];
}

function saveImage() {
  if (!isSourceReady()) {
    setStatus("Choose a photo or wait for the camera preview before saving.");
    return;
  }
  const [width, height] = getSourceDimensions();
  if (!width || !height || width * height > 40000000) {
    setStatus("This image size is not supported for local capture.");
    return;
  }
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) {
    setStatus("Image capture is unavailable in this browser.");
    return;
  }
  try {
    context.filter = activeFilter.cssFilter;
    context.drawImage(activeSource === "camera" ? elements.video : elements.image, 0, 0, width, height);
    context.filter = "none";
    drawDecorativeOverlay(context, width, height, activeFilter.effect);
    if (!elements.overlayCanvas.hidden && elements.overlayCanvas.width === width && elements.overlayCanvas.height === height) {
      context.drawImage(elements.overlayCanvas, 0, 0, width, height);
    }
    canvas.toBlob((blob) => {
      if (!blob) {
        setStatus("The browser could not create the image. Try a smaller photo.");
        return;
      }
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "cirvanna-living-filter-" + activeFilter.id + ".png";
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setStatus("Filtered image saved to your device. No copy was sent to Cirvanna.");
    }, "image/png");
  } catch {
    setStatus("Capture failed in this browser. Your original media has not been uploaded.");
  }
}

elements.file.addEventListener("change", (event) => loadPhoto(event.currentTarget.files?.[0]));
elements.startCamera.addEventListener("click", startCamera);
elements.stopCamera.addEventListener("click", stopCamera);
elements.capture.addEventListener("click", saveImage);
elements.arStart.addEventListener("click", startVision);
elements.arStop.addEventListener("click", () => stopVision());
elements.arConsent.addEventListener("change", () => {
  if (!elements.arConsent.checked) {
    stopVision("Consent withdrawn. Local face and hair processing stopped.");
  } else {
    updateARControls();
    setARStatus("Opt-in recorded for this page session. Start try-on when a photo or camera preview is ready.");
  }
});
elements.arModeGrid.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-ar-mode]");
  if (button && !button.disabled) selectAREffect(button.dataset.arMode);
});
elements.video.addEventListener("loadeddata", () => {
  if (activeSource === "camera") elements.capture.disabled = false;
  updateARControls();
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    if (cameraStream) stopCamera();
    else stopVision("Page hidden. Local face/hair processing was stopped.");
  }
});
window.addEventListener("pagehide", () => {
  stopCamera();
  stopVision("Page closed. Local face/hair processing was stopped.", false);
  releaseUploadedPhoto();
});

renderFilterButtons();
applyFilter(activeFilter);
updateARControls();