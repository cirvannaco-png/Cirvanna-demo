(() => {
  "use strict";
  const state = { base: "/api/commerce", token: "", merchants: [], decisions: [], inventory: null };
  const $ = id => document.getElementById(id);
  const notice = $("notice");
  const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({
    "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
  })[char]);
  const notify = (message, type) => { notice.textContent = message; notice.className = ("notice " + (type || "")).trim(); };
  const clearNotice = () => { notice.textContent = ""; notice.className = "notice hidden"; };
  function resolveBase(value) {
    if (!value.trim()) return "/api/commerce";
    const url = new URL(value.trim(), location.origin);
    if (url.origin !== location.origin || url.username || url.password || url.search || url.hash) {
      throw new Error("For security, this console accepts only its same-origin Commerce API.");
    }
    return url.pathname.replace(/\/+$/, "");
  }
  async function api(path, options) {
    const opts = options || {};
    const headers = { "Accept": "application/json", "Authorization": "Bearer " + state.token };
    const request = { method: opts.method || "GET", headers: headers, cache: "no-store", credentials: "omit", redirect: "error" };
    if (opts.body !== undefined) { headers["Content-Type"] = "application/json"; request.body = JSON.stringify(opts.body); }
    let response;
    try { response = await fetch(state.base + path, request); }
    catch (_) { throw new Error("Commerce could not be reached. Check the portal deployment and service readiness."); }
    const data = response.status === 204 ? null : await response.json().catch(() => null);
    if (!response.ok) {
      const detail = data && data.detail;
      const code = detail && typeof detail === "object" ? detail.code : (typeof detail === "string" ? detail : "REQUEST_FAILED");
      const error = new Error(code + " (HTTP " + response.status + ")");
      error.code = code; error.status = response.status; throw error;
    }
    return data;
  }
  const pill = value => {
    const s = String(value || "unknown").toLowerCase();
    return '<span class="status ' + esc(s) + '">' + esc(s.replaceAll("_", " ")) + '</span>';
  };
  const number = value => Number(value || 0).toLocaleString();
  async function connect() {
    clearNotice();
    state.base = resolveBase($("apiBase").value);
    state.token = $("token").value.trim();
    if (!state.token) throw new Error("A signed administrator access token is required.");
    const actor = await api("/me");
    if (!actor || actor.role !== "admin") throw new Error("Access denied: the verified identity does not carry the trusted admin role.");
    $("actor").textContent = "Verified administrator · " + (actor.email || actor.user_id);
    $("connect").classList.add("hidden"); $("workspace").classList.remove("hidden");
    await load();
    notify("Administrator verified. Commerce authorizes each decision and records its history.", "success");
  }
  async function load() {
    const query = new URLSearchParams({ offset: "0", limit: "100" });
    if ($("filter").value) query.set("state", $("filter").value);
    const values = await Promise.all([
      api("/admin/merchants?" + query.toString()),
      api("/admin/merchant-decisions?offset=0&limit=25"),
      api("/admin/inventory/audit")
    ]);
    state.merchants = Array.isArray(values[0] && values[0].items) ? values[0].items : [];
    state.decisions = Array.isArray(values[1] && values[1].items) ? values[1].items : [];
    state.inventory = values[2];
    render(Number(values[0] && values[0].total || 0));
  }
  function render(total) {
    const counts = { pending: 0, approved: 0, rejected: 0, suspended: 0 };
    state.merchants.forEach(item => { if (Object.prototype.hasOwnProperty.call(counts, item.status)) counts[item.status]++; });
    $("pending").textContent = number(counts.pending);
    $("approved").textContent = number(counts.approved);
    $("restricted").textContent = number(counts.rejected + counts.suspended);
    const violations = state.inventory && Array.isArray(state.inventory.violations) ? state.inventory.violations : [];
    $("violations").textContent = number(violations.length);
    $("merchants").innerHTML = state.merchants.length ? '<table><thead><tr><th>Brand / contact</th><th>Legal entity</th><th>Country</th><th>Status</th><th>Submitted</th><th>Decision</th></tr></thead><tbody>' +
      state.merchants.map(item => {
        let actions = "";
        if (item.status === "pending") {
          actions = '<button type="button" class="secondary" data-id="' + esc(item.merchant_id) + '" data-action="approve">Review</button>';
        } else if (item.status === "approved") {
          actions = '<button type="button" class="secondary" data-id="' + esc(item.merchant_id) + '" data-action="suspend">Suspend</button>';
        } else if (item.status === "suspended" || item.status === "rejected") {
          actions = '<button type="button" class="secondary" data-id="' + esc(item.merchant_id) + '" data-action="approve">Re-approve</button>';
        }
        return '<tr><td><b>' + esc(item.display_name) + '</b><div class="sub">' + esc(item.contact_email) + '</div><div class="sub mono">' + esc(item.merchant_id) + '</div></td>' +
          '<td>' + esc(item.legal_name) + '</td><td>' + esc(item.country_code) + '</td><td>' + pill(item.status) +
          '</td><td>' + esc(item.created_at ? new Date(item.created_at).toLocaleDateString() : "—") +
          '</td><td><div class="actions">' + actions + '</div></td></tr>';
      }).join("") + '</tbody></table>' : '<p class="muted">No merchant applications match this filter.</p>';
    $("merchants").setAttribute("aria-label", "Showing " + state.merchants.length + " of " + total + " merchants in this page.");
    $("decisions").innerHTML = state.decisions.length ? '<table><thead><tr><th>When</th><th>Merchant</th><th>Transition</th><th>Administrator</th></tr></thead><tbody>' +
      state.decisions.map(item => '<tr><td>' + esc(item.occurred_at ? new Date(item.occurred_at).toLocaleString() : "—") +
        '</td><td>' + esc(item.display_name) + '<div class="sub mono">' + esc(item.merchant_id) + '</div></td><td>' +
        pill(item.previous_state) + ' → ' + pill(item.new_state) + '<div class="sub">' + esc(item.decision) + ' · ' +
        number(item.commission_bps) + ' bps</div></td><td>' + esc(item.actor_user_id) +
        '<div class="sub">' + esc(item.note || item.verification_reference || "—") + '</div></td></tr>').join("") +
      '</tbody></table>' : '<p class="muted">No decisions recorded.</p>';
    $("inventoryStatus").textContent = state.inventory && state.inventory.ok === true ?
      "Inventory invariants are clean." : "Inventory audit found " + violations.length + " violation(s).";
    $("inventoryStatus").className = "notice " + (state.inventory && state.inventory.ok === true ? "success" : "error");
    $("inventory").innerHTML = violations.length ? '<table><thead><tr><th>Variant</th><th>On hand</th><th>Reserved</th><th>Version</th></tr></thead><tbody>' +
      violations.map(item => '<tr><td class="mono">' + esc(item.variant_id) + '</td><td>' + number(item.on_hand) +
        '</td><td>' + number(item.reserved_qty) + '</td><td>' + number(item.version) + '</td></tr>').join("") +
      '</tbody></table>' : '<p class="muted">No inventory invariant violations reported.</p>';
  }
  function openDecision(id, action) {
    const merchant = state.merchants.find(item => item.merchant_id === id);
    if (!merchant) return;
    $("merchantId").value = id; $("decision").value = action;
    $("decisionTitle").textContent = action.charAt(0).toUpperCase() + action.slice(1) + " merchant";
    $("decisionMerchant").textContent = merchant.display_name + " · " + merchant.legal_name;
    $("commission").value = merchant.commission_bps ?? 300;
    $("note").value = ""; $("verification").value = "";
    $("verificationWrap").classList.toggle("hidden", action !== "approve");
    $("verification").required = action === "approve";
    $("decisionDialog").showModal();
  }
  async function submitDecision(event) {
    event.preventDefault();
    const action = $("decision").value;
    const commission = Number($("commission").value);
    if (!Number.isInteger(commission) || commission < 0 || commission > 3000) {
      throw new Error("Commission must be an integer from 0 to 3000 basis points.");
    }
    const body = { decision: action, commission_bps: commission, note: $("note").value.trim() || null };
    if (action === "approve") {
      const reference = $("verification").value.trim();
      if (reference.length < 3) throw new Error("An external verification reference is required before approval.");
      body.verification_reference = reference;
    }
    await api("/admin/merchants/" + encodeURIComponent($("merchantId").value) + "/decision", { method: "POST", body: body });
    $("decisionDialog").close();
    await load();
    notify("Merchant decision recorded and appended to the audit history.", "success");
  }
  async function run(action) {
    clearNotice();
    try { await action(); }
    catch (error) { notify(error.message || "Request failed.", "error"); }
  }
  $("connectForm").addEventListener("submit", event => { event.preventDefault(); run(connect); });
  $("reload").addEventListener("click", () => run(load));
  $("filter").addEventListener("change", () => run(load));
  $("merchants").addEventListener("click", event => {
    const button = event.target.closest("[data-id][data-action]");
    if (button) openDecision(button.dataset.id, button.dataset.action);
  });
  $("decisionForm").addEventListener("submit", event => run(() => submitDecision(event)));
  document.querySelectorAll("[data-close]").forEach(button =>
    button.addEventListener("click", () => $("decisionDialog").close()));
  $("decisionDialog").addEventListener("click", event => {
    if (event.target === $("decisionDialog")) $("decisionDialog").close();
  });
  $("signout").addEventListener("click", () => {
    state.base = "/api/commerce"; state.token = ""; state.merchants = []; state.decisions = []; state.inventory = null;
    $("token").value = ""; $("workspace").classList.add("hidden");
    $("connect").classList.remove("hidden"); clearNotice();
  });
})();