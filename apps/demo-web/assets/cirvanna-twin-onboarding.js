(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const connectButton = $("connectSession");
  const tokenInput = $("sessionToken");
  const statusNode = $("sessionStatus");
  const capabilityGrid = $("capabilityGrid");
  const captureButton = $("startCapture");
  let bearer = "";

  const requiredBooleans = [
    "persistent_twin_generation",
    "persistent_twin_preview",
    "pose_skeleton_inference",
    "body_reconstruction",
    "full_surface_mesh",
    "calibrated_body_measurements",
    "image_persistence",
    "try_on_available"
  ];

  const capabilityLabels = [
    ["persistent_twin_generation", "Persistent Twin generation"],
    ["persistent_twin_preview", "Persistent Twin preview"],
    ["pose_skeleton_inference", "Ephemeral pose inference"],
    ["body_reconstruction", "Body reconstruction"],
    ["full_surface_mesh", "Validated full-body mesh"],
    ["calibrated_body_measurements", "Calibrated measurements"],
    ["image_persistence", "Private image persistence"],
    ["try_on_available", "Virtual try-on"]
  ];

  function setStatus(message, kind = "") {
    statusNode.textContent = message;
    statusNode.dataset.kind = kind;
  }

  async function loadSavedTwin(token) {
    const statusNode = $("savedTwinStatus");
    const details = $("savedTwinDetails");
    details.replaceChildren();
    statusNode.textContent = "Checking your owner-scoped Twin Registry record. This does not request or display any private image asset.";
    statusNode.dataset.kind = "";

    try {
      const response = await fetch("/api/virtual-twin/me", {
        method: "GET",
        headers: {
          Accept: "application/json",
          Authorization: "Bearer " + token
        },
        cache: "no-store",
        credentials: "same-origin"
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const code = data?.detail?.code || data?.detail || ("HTTP " + response.status);
        const messages = {
          TWIN_REGISTRY_API_URL_NOT_CONFIGURED: "The private Twin Registry is not configured in this environment yet.",
          TWIN_REGISTRY_API_TOKEN_NOT_CONFIGURED: "The private Twin Registry credentials are not configured yet.",
          TWIN_REGISTRY_UNAVAILABLE: "The private Twin Registry is temporarily unavailable.",
          TWIN_REGISTRY_LIST_TIMEOUT: "The Twin Registry did not respond in time."
        };
        throw new Error(typeof code === "string" ? (messages[code] || code) : JSON.stringify(code));
      }
      if (!data || !Array.isArray(data.twins) || data.count !== data.twins.length) {
        throw new Error("TWIN_REGISTRY_RESPONSE_INVALID");
      }
      if (data.twins.length === 0) {
        statusNode.textContent = "No currently authorized persistent Twin record was returned for this account. The Blue Flame remains your Cirvanna identity.";
        return;
      }

      const activeCount = data.twins.filter((twin) => twin.status === "active").length;
      statusNode.textContent = activeCount === 1
        ? "One active persistent Twin is authorized for this account."
        : activeCount > 1
          ? activeCount + " active persistent Twins are authorized for this account."
          : "No active persistent Twin is currently authorized. Historical or deletion-state records may still be listed below.";
      statusNode.dataset.kind = activeCount > 0 ? "good" : "";

      for (const twin of data.twins) {
        const card = document.createElement("article");
        card.className = "to-twin-record";
        const meta = document.createElement("div");
        const title = document.createElement("strong");
        title.textContent = twin.status === "active" ? "Persistent Twin · " + twin.twin_id : "Historical Twin record · " + twin.twin_id;
        const model = document.createElement("span");
        model.textContent = (twin.model_id || "Model") + " · revision " + (twin.model_revision || "unavailable");
        const created = document.createElement("span");
        created.textContent = "Created " + twin.created_at + " · record version " + twin.version;
        meta.append(title, model, created);
        const badge = document.createElement("span");
        badge.className = "to-twin-badge" + (twin.status === "active" ? " is-active" : " is-historical");
        badge.textContent = twin.status;
        card.append(meta, badge);
        details.append(card);
      }

      const note = document.createElement("p");
      note.className = "to-footnote";
      note.textContent = "Registry metadata only. A private mesh preview/readback route has not yet been released, so this page does not render or download your Twin asset.";
      details.append(note);
    } catch (error) {
      statusNode.textContent = "The Twin Registry could not confirm a saved Twin (" + (error instanceof Error ? error.message : "unavailable") + "). This is not proof that no Twin exists. The Blue Flame remains until the registry can be checked.";
      statusNode.dataset.kind = "error";
    }
  }

  function renderCapabilities(data) {
    capabilityGrid.replaceChildren();
    for (const [key, label] of capabilityLabels) {
      const item = document.createElement("div");
      item.className = "to-capability";
      const name = document.createElement("span");
      name.textContent = label;
      const state = document.createElement("span");
      state.className = "to-state";
      state.dataset.ready = String(data[key]);
      state.textContent = data[key] ? "Available" : "Unavailable";
      item.append(name, state);
      capabilityGrid.append(item);
    }

    const persistentReady =
      data.persistent_twin_generation === true &&
      data.persistent_twin_preview === true &&
      data.body_reconstruction === true &&
      data.full_surface_mesh === true &&
      data.image_persistence === true;

    captureButton.disabled = true;
    captureButton.textContent = "Capture is not enabled";
    if (persistentReady) {
      setStatus(
        "The service reports persistent Twin capabilities, but this demo has no owner-scoped Twin creation or status endpoint yet. Capture remains locked until that complete BFF workflow is implemented and verified.",
        "good"
      );
    } else {
      setStatus(
        "Your session is verified. The current service does not provide persistent Twin generation, a validated body mesh, or private image persistence. No photo or video has been uploaded.",
        ""
      );
    }
  }

  async function connect() {
    const token = bearer || tokenInput.value.trim();
    if (!token) {
      setStatus("Enter a short-lived signed customer session token. Do not use an admin or service credential.", "error");
      tokenInput.focus();
      return;
    }

    connectButton.disabled = true;
    connectButton.textContent = "Checking…";
    setStatus("Verifying your signed-in account and checking the live Twin capability contract.");

    try {
      const response = await fetch("/api/virtual-twin/capabilities", {
        method: "GET",
        headers: {
          Accept: "application/json",
          Authorization: "Bearer " + token
        },
        cache: "no-store",
        credentials: "same-origin"
      });
      const data = await response.json().catch(() => ({}));

      if (response.status === 401) {
        throw new Error("Your session could not be verified. Sign in again with a valid customer account.");
      }
      if (!response.ok) {
        const code = data?.detail?.code || data?.detail || ("HTTP " + response.status);
        throw new Error(typeof code === "string" ? code : JSON.stringify(code));
      }
      if (!data || data.service !== "virtual-twin" ||
          requiredBooleans.some((key) => typeof data[key] !== "boolean")) {
        throw new Error("The Twin service returned an incomplete capability response. Capture remains locked.");
      }

      bearer = token;
      tokenInput.value = "";
      tokenInput.placeholder = "Session verified for this page only";
      tokenInput.disabled = true;
      connectButton.textContent = "Refresh capability check";
      connectButton.disabled = false;
      renderCapabilities(data);
      await loadSavedTwin(token);
    } catch (error) {
      bearer = "";
      tokenInput.disabled = false;
      tokenInput.value = "";
      tokenInput.placeholder = "Paste a signed customer session token";
      setStatus(error instanceof Error ? error.message : "Could not verify your session or Twin service.", "error");
      connectButton.disabled = false;
      connectButton.textContent = "Verify session";
    }
  }

  connectButton.addEventListener("click", connect);
})();
