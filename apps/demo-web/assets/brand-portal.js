(() => {
  "use strict";
  const state = { base: "/api/commerce", token: "", actor: null, merchant: null, listings: [], orders: [], shopify: null, staged: [] };
  const $ = id => document.getElementById(id);
  const notice = $("notice");
  const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({
    "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
  })[char]);
  const notify = (message, type) => {
    notice.textContent = message;
    notice.className = ("notice " + (type || "")).trim();
  };
  const clearNotice = () => { notice.textContent = ""; notice.className = "notice hidden"; };
  function resolveBase(value) {
    if (!value.trim()) return "/api/commerce";
    const url = new URL(value.trim(), location.origin);
    if (url.origin !== location.origin || url.username || url.password || url.search || url.hash) {
      throw new Error("For security, this portal accepts only its same-origin Commerce API.");
    }
    return url.pathname.replace(/\/+$/, "");
  }
  async function api(path, options) {
    const opts = options || {};
    const headers = { "Accept": "application/json", "Authorization": "Bearer " + state.token };
    const request = {
      method: opts.method || "GET", headers: headers, cache: "no-store",
      credentials: "omit", redirect: "error"
    };
    if (opts.body !== undefined) {
      headers["Content-Type"] = "application/json";
      request.body = JSON.stringify(opts.body);
    }
    let response;
    try { response = await fetch(state.base + path, request); }
    catch (_) { throw new Error("Commerce could not be reached. Check the portal deployment and service readiness."); }
    const data = response.status === 204 ? null : await response.json().catch(() => null);
    if (!response.ok) {
      const detail = data && data.detail;
      const code = detail && typeof detail === "object" ? detail.code : (typeof detail === "string" ? detail : "REQUEST_FAILED");
      const error = new Error(code + " (HTTP " + response.status + ")");
      error.code = code; error.status = response.status;
      throw error;
    }
    return data;
  }
  function statusPill(value) {
    const safe = String(value || "unknown").toLowerCase();
    return '<span class="status ' + esc(safe) + '">' + esc(safe.replaceAll("_", " ")) + '</span>';
  }
  function currencyScale(currency) {
    const code = String(currency || "KES").toUpperCase();
    try {
      return Math.pow(10, new Intl.NumberFormat("en", { style: "currency", currency: code })
        .resolvedOptions().maximumFractionDigits);
    } catch (_) { throw new Error("Unsupported ISO currency code: " + code); }
  }
  function money(minor, currency) {
    const code = String(currency || "KES").toUpperCase();
    return new Intl.NumberFormat("en-KE", { style: "currency", currency: code })
      .format(Number(minor || 0) / currencyScale(code));
  }
  function hidePanels() {
    ["application", "applicationStatus", "seller"].forEach(id => $(id).classList.add("hidden"));
  }
  async function loadAccount() {
    const merchant = await api("/merchants/me");
    state.merchant = merchant;
    $("merchantName").textContent = merchant.display_name || "Merchant workspace";
    $("merchantMeta").textContent = [merchant.country_code, merchant.contact_email, merchant.merchant_id].filter(Boolean).join(" · ");
    $("merchantStatus").innerHTML = statusPill(merchant.status);
    hidePanels();
    if (merchant.status === "pending") {
      $("statusTitle").textContent = "Application under review";
      $("statusMessage").textContent = "Commerce has recorded the application. External verification and administrator approval are still required.";
      $("applicationStatus").classList.remove("hidden");
    } else if (["rejected", "suspended"].includes(merchant.status)) {
      $("statusTitle").textContent = "Merchant account " + merchant.status;
      $("statusMessage").textContent = merchant.decision_note || "Contact Cirvanna support for further information.";
      $("applicationStatus").classList.remove("hidden");
    } else if (merchant.status === "approved" && state.actor.role !== "merchant") {
      $("statusTitle").textContent = "Approval recorded · identity update required";
      $("statusMessage").textContent = "The merchant record is approved, but this access token does not carry the merchant role. Sign out and reconnect after Cirvanna Identity issues a fresh merchant-role token.";
      $("applicationStatus").classList.remove("hidden");
    } else if (merchant.status === "approved") {
      $("seller").classList.remove("hidden");
      await loadDashboard();
    }
  }
  async function connect() {
    clearNotice();
    state.base = resolveBase($("apiBase").value);
    state.token = $("token").value.trim();
    if (!state.token) throw new Error("A signed access token is required.");
    state.actor = await api("/me");
    if (!state.actor || typeof state.actor.user_id !== "string") throw new Error("Commerce did not return a valid authenticated identity.");
    $("connect").classList.add("hidden");
    $("workspace").classList.remove("hidden");
    $("signout").classList.remove("hidden");
    try {
      await loadAccount();
      notify("Connected as " + state.actor.role + ". Commerce authorizes every seller operation.", "success");
    } catch (error) {
      if (error.status === 404 && error.code === "MERCHANT_APPLICATION_NOT_FOUND") {
        $("merchantName").textContent = "Merchant onboarding";
        $("merchantMeta").textContent = "Signed-in account · " + state.actor.role;
        $("merchantStatus").textContent = "No application";
        hidePanels();
        $("application").classList.remove("hidden");
      } else { throw error; }
    }
  }
  async function loadDashboard() {
    const values = await Promise.all([
      api("/merchant/listings?offset=0&limit=50"),
      api("/merchant/orders?offset=0&limit=20")
    ]);
    state.listings = Array.isArray(values[0] && values[0].items) ? values[0].items : [];
    state.orders = Array.isArray(values[1] && values[1].items) ? values[1].items : [];
    renderListings();
    renderOrders();
    await loadShopifyConnection();
    const variants = state.listings.flatMap(item => item.variants || []);
    $("mListings").textContent = state.listings.length.toLocaleString();
    $("mVariants").textContent = variants.length.toLocaleString();
    $("mStock").textContent = variants.reduce((sum, item) => sum + Number(item.available_stock || 0), 0).toLocaleString();
    $("mOrders").textContent = state.orders.length.toLocaleString();
  }
  function renderListings() {
    const root = $("listings");
    if (!state.listings.length) {
      root.innerHTML = '<p class="muted">No catalog listings linked yet.</p>';
      return;
    }
    root.innerHTML = state.listings.map(listing => {
      const variants = (listing.variants || []).map(variant =>
        '<tr><td><b>' + esc(variant.sku) + '</b><div class="sub">' + esc(JSON.stringify(variant.options || {})) + '</div></td>' +
        '<td>' + esc(money(variant.price_minor, variant.currency)) + '</td>' +
        '<td>' + Number(variant.on_hand || 0) + ' on hand<br><span class="sub">' + Number(variant.reserved_qty || 0) + ' reserved</span></td>' +
        '<td>' + Number(variant.available_stock || 0) + '</td><td>' + statusPill(variant.state) + '</td>' +
        '<td><button type="button" class="secondary" data-stock="' + esc(variant.variant_id) + '" data-sku="' + esc(variant.sku) + '">Adjust</button></td></tr>'
      ).join("") || '<tr><td colspan="6">No variants have been created for this listing.</td></tr>';
      return '<article class="listing"><div class="row"><div><h3>' + esc(listing.product_name) + '</h3>' +
        '<div class="sub">' + esc(listing.category) + ' · Catalog ' + esc(listing.catalog_product_id) + '</div></div>' +
        statusPill(listing.status) + '</div><div class="scroll"><table><thead><tr><th>SKU / options</th><th>Price</th>' +
        '<th>Inventory</th><th>Available</th><th>State</th><th>Action</th></tr></thead><tbody>' + variants +
        '</tbody></table></div><p><button type="button" data-variant="' + esc(listing.listing_id) +
        '" data-title="' + esc(listing.product_name) + '">Add variant</button></p></article>';
    }).join("");
  }
  function renderOrders() {
    const root = $("orders");
    if (!state.orders.length) {
      root.innerHTML = '<p class="muted">No merchant orders in the latest page.</p>';
      return;
    }
    root.innerHTML = '<table><thead><tr><th>Order</th><th>Created</th><th>Your items</th><th>Your subtotal</th><th>Status</th><th>Payment</th></tr></thead><tbody>' +
      state.orders.map(order => {
        const items = (order.items || []).map(item => Number(item.quantity || 0) + ' × ' + esc(item.product_name) + ' (' + esc(item.sku) + ')').join("<br>");
        return '<tr><td>' + esc(order.order_number || order.order_id) + '</td><td>' +
          esc(order.created_at ? new Date(order.created_at).toLocaleDateString() : "—") + '</td><td>' + (items || "—") +
          '</td><td>' + esc(money(order.subtotal_minor, order.currency)) + '</td><td>' + statusPill(order.status) +
          '</td><td>' + statusPill(order.payment_status) + '</td></tr>';
      }).join("") + '</tbody></table>';
  }
  async function loadShopifyConnection() {
    const data = await api("/integrations/shopify/connection");
    state.shopify = data;
    $("shopifyStatus").textContent = data.connected ? (data.status || "connected") : "not connected";
    $("shopifyMeta").textContent = data.configured
      ? [data.shop_name || data.shop_domain, data.shop_currency, data.status, data.webhooks_complete ? "webhooks registered" : "webhook setup incomplete", data.products_synced_at ? "last sync " + new Date(data.products_synced_at).toLocaleString() : "not synced"].filter(Boolean).join(" · ")
      : "No Shopify store connected. OAuth and webhook configuration must be enabled by Cirvanna operations.";
    $("shopifySync").disabled = !data.connected;
    $("shopifyReload").disabled = !data.connected;
    $("shopifyDisconnect").disabled = data.configured !== true;
    if (data.connected) await loadShopifyStaged();
    else {
      state.staged = [];
      $("shopifyStaged").innerHTML = '<p class="muted">Connect a store and run the first sync to stage products privately.</p>';
    }
  }
  async function loadShopifyStaged() {
    const data = await api("/integrations/shopify/staged-products?offset=0&limit=50");
    state.staged = Array.isArray(data.items) ? data.items : [];
    renderShopifyStaged();
  }
  function renderShopifyStaged() {
    const root = $("shopifyStaged");
    if (!state.staged.length) {
      root.innerHTML = '<p class="muted">No staged products in the latest page.</p>';
      return;
    }
    root.innerHTML = state.staged.map(product => {
      const variants = (product.variants || []).map(variant =>
        '<label class="wide">' + esc(variant.sku || variant.title || "Variant") + ' · ' +
        esc(variant.currency) + ' · ' + esc(variant.tracked && variant.inventory_complete ? String(variant.available_quantity) + ' available' : 'inventory unverified') +
        '<input data-shopify-variant="' + esc(variant.shopify_variant_gid) + '" placeholder="Canonical Catalog variant UUID" value="' +
        esc(variant.canonical_variant_id || "") + '"></label>'
      ).join("");
      const ready = product.remote_status === "ACTIVE" && product.variants_complete;
      return '<article class="listing" data-shopify-snapshot="' + esc(product.snapshot_id) + '"><div class="row"><div><h3>' +
        esc(product.title) + '</h3><div class="sub">' + esc(product.vendor || "Shopify") + ' · ' +
        esc(product.product_type || "Uncategorized") + ' · ' + esc(product.remote_status) + '</div></div>' +
        statusPill(product.mapping_state) + '</div><p class="sub">' + (ready ? "Variant set complete. Map to an existing Catalog product and exact variants." : "Mapping disabled until an active, complete variant set is synchronized.") + '</p>' +
        '<label class="wide">Canonical Catalog product UUID<input data-canonical-product placeholder="Existing Catalog product UUID"></label>' +
        '<div class="grid">' + variants + '</div><button type="button" data-shopify-map ' + (ready ? "" : "disabled") + '>Map variants to Catalog</button>' +
        (ready && product.mapping_state === "mapped" ? '<button type="button" class="secondary" data-shopify-reactivate>Confirm / reactivate mapped listing</button>' : '') +
        '</article>';
    }).join("");
  }
  async function startShopifyOAuth(event) {
    event.preventDefault();
    const domain = $("shopifyDomain").value.trim().toLowerCase();
    if (!/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.myshopify\.com$/.test(domain)) {
      throw new Error("Enter the canonical your-store.myshopify.com domain.");
    }
    const response = await fetch(state.base + "/integrations/shopify/install?shop=" + encodeURIComponent(domain), {
      method: "GET", headers: { "Accept": "application/json", "Authorization": "Bearer " + state.token },
      cache: "no-store", credentials: "same-origin", redirect: "manual"
    });
    if (response.status !== 302) {
      const data = await response.json().catch(() => null);
      const detail = data && data.detail;
      const code = detail && typeof detail === "object" ? detail.code : (detail || "SHOPIFY_OAUTH_START_FAILED");
      throw new Error(String(code) + " (HTTP " + response.status + ")");
    }
    const location = response.headers.get("Location");
    if (!location || !location.startsWith("https://" + domain + "/admin/oauth/authorize?")) {
      throw new Error("Shopify did not return a valid authorization destination.");
    }
    window.location.assign(location);
  }
  async function syncShopify() {
    const result = await api("/integrations/shopify/sync/products", { method: "POST" });
    await loadShopifyConnection();
    notify("Shopify sync processed " + Number(result.variants_seen || 0) + " variants. Products remain private until Catalog mapping and CAL authorization.", "success");
  }
  async function disconnectShopify() {
    if (!window.confirm("Disconnect this Shopify store from Cirvanna? Existing imported orders remain in Cirvanna records.")) return;
    await api("/integrations/shopify/disconnect", { method: "POST" });
    await loadShopifyConnection();
    notify("Shopify connection revoked. Reconnect through OAuth to resume synchronization.", "success");
  }
  async function reactivateShopifyProduct(article) {
    const snapshotId = article.dataset.shopifySnapshot;
    if (!window.confirm("Reactivate this mapped Commerce listing and its verified Shopify variants? CAL will still decide whether shoppers may see it.")) return;
    const result = await api("/integrations/shopify/products/" + encodeURIComponent(snapshotId) + "/reactivate", { method: "POST" });
    await loadDashboard();
    notify("Listing reactivated for " + Number(result.variant_count || 0) + " mapped variants. Shopper display still requires CAL SHOW.", "success");
  }
  async function mapShopifyProduct(article) {
    const snapshotId = article.dataset.shopifySnapshot;
    const canonicalProductId = article.querySelector("[data-canonical-product]").value.trim();
    const variantInputs = Array.from(article.querySelectorAll("[data-shopify-variant]"));
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(canonicalProductId)) {
      throw new Error("Enter a valid existing Catalog product UUID.");
    }
    if (!variantInputs.length || variantInputs.some(input => !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(input.value.trim()))) {
      throw new Error("Enter a canonical Catalog variant UUID for every Shopify variant.");
    }
    await api("/integrations/shopify/products/" + encodeURIComponent(snapshotId) + "/map", {
      method: "POST",
      body: {
        canonical_product_id: canonicalProductId,
        variants: variantInputs.map(input => ({
          shopify_variant_gid: input.dataset.shopifyVariant,
          canonical_variant_id: input.value.trim()
        }))
      }
    });
    await loadShopifyStaged();
    await loadDashboard();
    notify("Shopify variants mapped to canonical Catalog identities. Shopper display still requires CAL SHOW.", "success");
  }

  async function submitApplication(event) {
    event.preventDefault();
    await api("/merchants/applications", { method: "POST", body: {
      display_name: $("displayName").value.trim(), legal_name: $("legalName").value.trim(),
      country_code: $("countryCode").value.trim().toUpperCase(), contact_email: $("contactEmail").value.trim()
    }});
    await loadAccount();
    notify("Merchant application submitted. Privileges remain disabled pending verification, approval and identity-provider role issuance.", "success");
  }
  async function linkProduct(event) {
    event.preventDefault();
    const id = $("catalogId").value.trim();
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id)) {
      throw new Error("Enter a valid canonical Catalog product UUID.");
    }
    await api("/merchant/listings", { method: "POST", body: { catalog_product_id: id }});
    event.target.reset();
    await loadDashboard();
    notify("Catalog product linked. Add an active, in-stock variant before it becomes a purchasable offer.", "success");
  }
  async function addVariant(event) {
    event.preventDefault();
    let options;
    try { options = JSON.parse($("options").value); }
    catch (_) { throw new Error("Variant options must be valid JSON."); }
    if (!options || Array.isArray(options) || typeof options !== "object" ||
        Object.values(options).some(value => typeof value !== "string")) {
      throw new Error("Options must be a JSON object with string values.");
    }
    const price = Number($("price").value);
    const stock = Number($("initialStock").value);
    const currency = $("currency").value.trim().toUpperCase();
    if (!Number.isFinite(price) || price < 0 || !Number.isInteger(stock) || stock < 0) {
      throw new Error("Enter a valid price and whole-number stock amount.");
    }
    await api("/merchant/listings/" + encodeURIComponent($("variantListingId").value) + "/variants", {
      method: "POST", body: {
        sku: $("sku").value.trim(), options: options,
        price_minor: Math.round(price * currencyScale(currency)),
        currency: currency, initial_stock: stock
      }
    });
    $("variantDialog").close();
    event.target.reset();
    $("currency").value = "KES";
    $("options").value = '{"size":"M","colour":"Black"}';
    await loadDashboard();
    notify("Variant created and opening inventory recorded.", "success");
  }
  async function adjustStock(event) {
    event.preventDefault();
    const delta = Number($("stockDelta").value);
    const reason = $("stockReason").value.trim();
    if (!Number.isInteger(delta) || delta === 0 || reason.length < 3) {
      throw new Error("Enter a non-zero whole-number adjustment and a reason.");
    }
    await api("/merchant/variants/" + encodeURIComponent($("stockVariantId").value) + "/inventory-adjustments", {
      method: "POST", body: { quantity_delta: delta, reason: reason }
    });
    $("stockDialog").close();
    event.target.reset();
    await loadDashboard();
    notify("Inventory movement recorded by Commerce.", "success");
  }
  async function run(action) {
    clearNotice();
    try { await action(); }
    catch (error) {
      if (error.code === "MERCHANT_ROLE_REQUIRED") {
        notify("This token does not carry the merchant role. Reconnect with a fresh token issued by Cirvanna Identity.", "error");
      } else if (error.code === "MERCHANT_NOT_APPROVED") {
        notify("Merchant operations remain unavailable until the account is approved.", "error");
      } else { notify(error.message || "Request failed.", "error"); }
    }
  }
  $("connectForm").addEventListener("submit", event => { event.preventDefault(); run(connect); });
  $("applicationForm").addEventListener("submit", event => run(() => submitApplication(event)));
  $("shopifyConnectForm").addEventListener("submit", event => run(() => startShopifyOAuth(event)));
  $("shopifySync").addEventListener("click", () => run(syncShopify));
  $("shopifyReload").addEventListener("click", () => run(loadShopifyStaged));
  $("shopifyDisconnect").addEventListener("click", () => run(disconnectShopify));
  $("shopifyStaged").addEventListener("click", event => {
    const button = event.target.closest("[data-shopify-map]");
    const reactivate = event.target.closest("[data-shopify-reactivate]");
    if (button) run(() => mapShopifyProduct(button.closest("[data-shopify-snapshot]")));
    if (reactivate) run(() => reactivateShopifyProduct(reactivate.closest("[data-shopify-snapshot]")));
  });
  $("listingForm").addEventListener("submit", event => run(() => linkProduct(event)));
  $("variantForm").addEventListener("submit", event => run(() => addVariant(event)));
  $("stockForm").addEventListener("submit", event => run(() => adjustStock(event)));
  $("refreshStatus").addEventListener("click", () => run(loadAccount));
  $("reload").addEventListener("click", () => run(loadDashboard));
  $("listings").addEventListener("click", event => {
    const variant = event.target.closest("[data-variant]");
    const stock = event.target.closest("[data-stock]");
    if (variant) {
      $("variantListingId").value = variant.dataset.variant;
      $("variantProduct").textContent = variant.dataset.title;
      $("variantDialog").showModal();
    }
    if (stock) {
      $("stockVariantId").value = stock.dataset.stock;
      $("stockSku").textContent = stock.dataset.sku;
      $("stockDialog").showModal();
    }
  });
  document.querySelectorAll("[data-close]").forEach(button =>
    button.addEventListener("click", () => $(button.dataset.close).close()));
  ["variantDialog", "stockDialog"].forEach(id =>
    $(id).addEventListener("click", event => { if (event.target === $(id)) $(id).close(); }));
  $("signout").addEventListener("click", () => {
    state.base = "/api/commerce"; state.token = ""; state.actor = null; state.merchant = null;
    state.listings = []; state.orders = [];
    $("token").value = ""; $("workspace").classList.add("hidden");
    $("connect").classList.remove("hidden"); $("signout").classList.add("hidden"); clearNotice();
  });
})();