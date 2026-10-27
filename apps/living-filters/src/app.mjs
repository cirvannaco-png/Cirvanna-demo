import { FILTERS, getFilterById } from "./filter-catalog.mjs";

const elements = {
  stage: document.querySelector("#stage"),
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
};

let cameraStream = null;
let uploadedObjectUrl = null;
let activeSource = null;
let activeFilter = getFilterById("original");

function setStatus(message) {
  elements.status.textContent = message;
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
}

function stopCamera() {
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
  if (cameraStream) stopCamera();
  setStatus("Requesting camera permission…");
  elements.startCamera.disabled = true;
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { facingMode: { ideal: "user" }, width: { ideal: 1280 }, height: { ideal: 960 } },
    });
    elements.video.srcObject = cameraStream;
    await elements.video.play();
    releaseUploadedPhoto();
    showSource("camera");
    elements.capture.disabled = !isSourceReady();
    setStatus("Camera is active. Your video is processed locally and is not uploaded.");
  } catch (error) {
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
elements.video.addEventListener("loadeddata", () => {
  if (activeSource === "camera") elements.capture.disabled = false;
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden && cameraStream) stopCamera();
});
window.addEventListener("pagehide", () => {
  stopCamera();
  releaseUploadedPhoto();
});

renderFilterButtons();
applyFilter(activeFilter);