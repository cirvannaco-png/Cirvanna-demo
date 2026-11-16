(() => {
  "use strict";

  const root = document.getElementById("appearanceWorkspaceRoot");
  if (!root) return;

  const API = {
    consents: "/api/appearance/consents",
    renew: "/api/appearance/consents/renew",
    revoke: "/api/appearance/consents/revoke",
    looks: "/api/appearance/looks"
  };
  const COMPONENTS = [
    ["hairstyle","Hairstyle / cut"],["hair_colour","Hair colour"],["hairline","Hairline"],
    ["facial_hair","Facial hair / moustache"],["eyebrows","Eyebrows"],["eyelashes","Eyelashes"],
    ["lipstick","Lipstick"],["makeup","Makeup"],["skincare_application","Skincare application"],
    ["skincare_product","Skincare product"],["haircare_product","Haircare product"],
    ["garment","Clothing / garment"],["footwear","Footwear"],["jewellery","Jewellery"],
    ["eyewear","Eyewear / glasses"],["headwear","Hats / headwear"],["hair_accessory","Hair accessories"],
    ["bag","Bag"],["accessory","Other accessory"],["nail_art","Nail art"],["fragrance","Fragrance"]
  ];
  const MAX_SOURCE_BYTES = 10 * 1024 * 1024;

  let accessToken = "";
  let looks = [];
  let activeLook = null;
  let versions = [];

  const el = (tag, attributes = {}, content = null) => {
    const node = document.createElement(tag);
    for (const [key,value] of Object.entries(attributes)) {
      if (key === "className") node.className = value;
      else if (key === "text") node.textContent = String(value ?? "");
      else if (key === "onClick" && typeof value === "function") node.addEventListener("click",value);
      else if (value === true) node.setAttribute(key,"");
      else if (value !== false && value !== null && value !== undefined) node.setAttribute(key,String(value));
    }
    if (content !== null) {
      if (Array.isArray(content)) content.forEach(item => item && node.append(item));
      else if (content instanceof Node) node.append(content);
      else node.textContent = String(content);
    }
    return node;
  };
  const text = (tag,value,className) => el(tag,{className,text:value});
  const button = (label,handler,className,disabled=false) =>
    el("button",{type:"button",className:className||"aw-btn",disabled,onClick:handler},label);
  const field = (label,control,hint="") => {
    const wrap=el("label",{className:"aw-field"});
    wrap.append(text("span",label,"aw-label"),control);
    if(hint) wrap.append(text("small",hint,"aw-hint"));
    return wrap;
  };
  const check = (label,id) => {
    const input=el("input",{type:"checkbox",id});
    const wrap=el("label",{className:"aw-check"});
    wrap.append(input,text("span",label));
    return {wrap,input};
  };
  const status = (message,kind="") => {
    const node=document.getElementById("awStatus");
    if(!node) return;
    node.textContent=message;
    node.className="aw-status"+(kind?" "+kind:"");
  };
  const uuid = () => {
    if(globalThis.crypto && typeof crypto.randomUUID==="function") return crypto.randomUUID();
    return "aw-"+Date.now().toString(36)+"-"+Math.random().toString(36).slice(2,18);
  };
  const api = async (path,options={}) => {
    const headers={
      Accept:"application/json",
      ...(accessToken?{Authorization:"Bearer "+accessToken}:{}),
      ...(options.headers||{})
    };
    let body=options.body;
    if(body!==undefined && !(body instanceof FormData) && typeof body!=="string") {
      headers["Content-Type"]="application/json";
      body=JSON.stringify(body);
    }
    const response=await fetch(path,{
      method:options.method||"GET",
      headers,
      body,
      cache:"no-store",
      credentials:"same-origin"
    });
    if(response.status===204) return {status:"deleted"};
    const data=await response.json().catch(()=>({}));
    if(!response.ok) {
      const code=data?.detail?.code||data?.detail||("HTTP_"+response.status);
      const error=new Error(typeof code==="string"?code:JSON.stringify(code));
      error.status=response.status;
      throw error;
    }
    return data;
  };

  const css=[
    "#appearanceWorkspaceRoot{margin:20px 0 28px;scroll-margin-top:90px}",
    "#appearanceWorkspaceRoot .aw-panel{background:var(--panel,#171722);border:1px solid var(--line,#34313c);padding:18px;margin:0;border-radius:4px;color:var(--cream,#f0ebe2)}",
    "#appearanceWorkspaceRoot .aw-heading{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap}",
    "#appearanceWorkspaceRoot h2{font:26px Georgia,serif;font-weight:400;margin:0 0 7px}",
    "#appearanceWorkspaceRoot h3{font:20px Georgia,serif;font-weight:400;margin:0 0 8px}",
    "#appearanceWorkspaceRoot .aw-muted,#appearanceWorkspaceRoot .aw-hint{font-size:12px;color:var(--muted,#aaa5b1)}",
    "#appearanceWorkspaceRoot .aw-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px}",
    "#appearanceWorkspaceRoot .aw-field{display:flex;flex-direction:column;gap:5px;margin:8px 0}",
    "#appearanceWorkspaceRoot .aw-label{font-size:11px;color:var(--muted,#aaa5b1)}",
    "#appearanceWorkspaceRoot input:not([type=checkbox]),#appearanceWorkspaceRoot select,#appearanceWorkspaceRoot textarea{box-sizing:border-box;width:100%;min-width:0;padding:10px;background:#101018;border:1px solid var(--line,#34313c);color:var(--cream,#f0ebe2);border-radius:3px;font:inherit}",
    "#appearanceWorkspaceRoot textarea{min-height:76px;resize:vertical}",
    "#appearanceWorkspaceRoot .aw-checks{display:grid;gap:7px;margin:12px 0}",
    "#appearanceWorkspaceRoot .aw-check{display:flex;gap:8px;align-items:flex-start;color:var(--cream,#f0ebe2);font-size:12px}",
    "#appearanceWorkspaceRoot .aw-check input{margin-top:2px}",
    "#appearanceWorkspaceRoot .aw-btn{border:1px solid var(--line,#34313c);background:transparent;color:var(--cream,#f0ebe2);padding:8px 11px;border-radius:3px;font:inherit;font-size:12px;cursor:pointer}",
    "#appearanceWorkspaceRoot .aw-btn.primary{background:var(--gold,#c4924a);border-color:var(--gold,#c4924a);color:#17120a;font-weight:700}",
    "#appearanceWorkspaceRoot .aw-btn.danger{color:#e7a4a4;border-color:#704b4b}",
    "#appearanceWorkspaceRoot .aw-btn:disabled{opacity:.45;cursor:not-allowed}",
    "#appearanceWorkspaceRoot .aw-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}",
    "#appearanceWorkspaceRoot .aw-status{padding:10px 12px;margin:10px 0;background:#12121a;border-left:2px solid var(--gold,#c4924a);font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}",
    "#appearanceWorkspaceRoot .aw-status.error{border-color:#e7a4a4;color:#e7a4a4}",
    "#appearanceWorkspaceRoot .aw-status.good{border-color:#8bc8a3;color:#8bc8a3}",
    "#appearanceWorkspaceRoot .aw-list{display:grid;gap:8px;margin-top:10px}",
    "#appearanceWorkspaceRoot .aw-look{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:10px;border:1px solid var(--line,#34313c);background:#12121a}",
    "#appearanceWorkspaceRoot .aw-look-meta{min-width:0;font-size:12px;color:var(--muted,#aaa5b1)}",
    "#appearanceWorkspaceRoot .aw-op{border-top:1px solid var(--line,#34313c);padding:9px 0;font-size:12px}",
    "#appearanceWorkspaceRoot .aw-pill{display:inline-block;border:1px solid var(--line,#34313c);border-radius:20px;padding:3px 7px;font-size:10px;color:var(--gold,#c4924a);margin-right:5px}",
    "#appearanceWorkspaceRoot .aw-divider{border:0;border-top:1px solid var(--line,#34313c);margin:15px 0}",
    "#appearanceWorkspaceRoot .aw-hidden{display:none!important}",
    "@media(max-width:620px){#appearanceWorkspaceRoot .aw-grid{grid-template-columns:1fr}#appearanceWorkspaceRoot .aw-panel{padding:13px}#appearanceWorkspaceRoot .aw-look{align-items:flex-start;flex-direction:column}}"
  ].join("\n");
  document.head.append(el("style",{},css));

  const panel=el("section",{className:"aw-panel","aria-labelledby":"awTitle"});
  const intro=el("div",{className:"aw-heading"});
  const introText=el("div");
  introText.append(
    text("div","STYLE · GROOMING · COMPLETE APPEARANCE","aw-muted"),
    el("h2",{id:"awTitle",text:"Appearance workspace"}),
    text("p","One saved look shared across Wardrobe, PNELLY, Try-On, Virtual Twin and Marketplace. Your instructions remain yours; every edit preserves unrequested regions.","aw-muted")
  );
  const connection=text("div","Connect a signed-in Cirvanna account to save and edit appearances.","aw-muted");
  intro.append(introText,connection);
  panel.append(intro);
  panel.append(text("div","Edits can be saved as a structured look plan now. Photorealistic rendering remains unavailable until validated, category-specific renderers pass identity, skin-tone and unaffected-region checks.","aw-status"));
  panel.append(el("div",{id:"awStatus",className:"aw-status",role:"status",text:"Not connected."}));

  const workspace=el("div",{id:"awWorkspace",className:"aw-hidden"});
  const cols=el("div",{className:"aw-grid"});
  const createCol=el("div",{className:"aw-column"});
  const listCol=el("div",{className:"aw-column"});
  createCol.append(text("h3","Start an appearance look"));
  listCol.append(text("h3","Your saved appearances"));

  const baseSelect=el("select",{id:"awBaseKind"});
  baseSelect.append(new Option("Upload a source photo","source_photo"),new Option("Use my existing Virtual Twin","virtual_twin"));
  const twinId=el("input",{id:"awTwinId",placeholder:"Existing Twin ID"});
  const file=el("input",{id:"awSourceFile",type:"file",accept:"image/jpeg,image/png,image/webp"});
  const sessionConsent=check("I agree to store this appearance look and its edit history.","awSessionConsent");
  const sourceConsent=check("I agree to retain this uploaded source photo in private storage for this look.","awSourceConsent");
  const processingConsent=check("I agree to process this source photo for the look instructions I submit.","awImageConsent");
  const createButton=button("Create appearance look",createLook,"aw-btn primary");
  const createForm=el("div");
  createForm.append(
    field("Starting point",baseSelect),
    field("Existing Twin ID",twinId,"Only an already-authorized persistent Twin can be used. No new Twin is fabricated here."),
    field("Original photo",file,"JPEG, PNG or WebP; maximum 10 MB. The image is read only after the required permissions are granted.")
  );
  const createChecks=el("div",{className:"aw-checks"});
  createChecks.append(sessionConsent.wrap,sourceConsent.wrap,processingConsent.wrap);
  createForm.append(createChecks,createButton);
  createCol.append(createForm);

  const listRoot=el("div",{id:"awSavedLooks",className:"aw-list"});
  const refreshButton=button("Refresh",loadLooks,"aw-btn");
  listCol.append(el("div",{className:"aw-row"},[refreshButton]),listRoot);
  cols.append(createCol,listCol);
  workspace.append(cols);

  const detail=el("section",{id:"awDetail",className:"aw-hidden"});
  detail.append(el("hr",{className:"aw-divider"}),text("h3","Selected appearance"));
  const detailMeta=text("p","Choose one saved look to inspect its edit history.","aw-muted");
  const renewalPane=el("div",{id:"awRenewalPane",className:"aw-hidden"});
  const operationRoot=el("div",{id:"awOperations"});
  const editForm=el("div",{id:"awEditForm"});
  const compareRoot=el("div",{id:"awCompare"});
  const actions=el("div",{className:"aw-row"});
  const resetButton=button("Reset to original",resetLook,"aw-btn");
  const undoButton=button("Undo selected version",undoLook,"aw-btn");
  const favoriteButton=button("Save favourite",toggleFavorite,"aw-btn");
  const revokeButton=button("Revoke look consent",revokeLookConsent,"aw-btn");
  const deleteButton=button("Delete look and private media",deleteLook,"aw-btn danger");
  actions.append(resetButton,undoButton,favoriteButton,revokeButton,deleteButton);
  const preview=el("div",{className:"aw-status",text:"Photorealistic preview unavailable: no validated appearance renderer is connected. This workspace stores your requested transformation plan; it will not claim that your image has changed."});
  detail.append(detailMeta,renewalPane,actions,operationRoot,editForm,compareRoot,preview);
  workspace.append(detail);
  panel.append(workspace);
  root.replaceChildren(panel);

  baseSelect.addEventListener("change",()=>{
    const photo=baseSelect.value==="source_photo";
    twinId.closest(".aw-field").classList.toggle("aw-hidden",photo);
    file.closest(".aw-field").classList.toggle("aw-hidden",!photo);
    sourceConsent.wrap.classList.toggle("aw-hidden",!photo);
    processingConsent.wrap.classList.toggle("aw-hidden",!photo);
  });
  baseSelect.dispatchEvent(new Event("change"));

  const componentSelect=el("select",{id:"awComponent"});
  COMPONENTS.forEach(([value,label])=>componentSelect.append(new Option(label,value)));
  const actionSelect=el("select",{id:"awAction"});
  [["apply","Apply"],["replace","Replace"],["adjust","Adjust"],["remove","Remove"]].forEach(([v,l])=>actionSelect.append(new Option(l,v)));
  const refKind=el("select",{id:"awReferenceKind"});
  refKind.append(new Option("No product or wardrobe reference",""),new Option("Catalog product (CAL-approved)","catalog_product"),new Option("My wardrobe item","wardrobe_item"),new Option("Style catalogue","style_catalog"));
  const refId=el("input",{id:"awReferenceId",placeholder:"Opaque product / wardrobe / style ID"});
  const description=el("textarea",{id:"awDescription",maxlength:"500",placeholder:"Describe the exact look you want: e.g. low taper with sponge twists; warm copper highlights; subtle brown lipstick."});
  const regionHint=el("input",{id:"awRegions",placeholder:"Optional region keys, comma-separated"});
  const editFields=el("div",{className:"aw-grid"});
  editFields.append(
    field("Appearance component",componentSelect),
    field("Action",actionSelect),
    field("Optional reference type",refKind),
    field("Reference ID",refId),
    field("Transformation instructions",description,"Only the named component is changed. Unrequested regions stay protected."),
    field("Optional target regions",regionHint,"Leave blank to use the component's default regions.")
  );
  const applyButton=button("Save this edit",applyOperation,"aw-btn primary");
  editForm.append(text("h3","Change one thing at a time"),editFields,el("div",{className:"aw-row"},[applyButton]));
  const versionSelect=el("select",{id:"awVersionSelect"});
  const compareSelect=el("select",{id:"awCompareSelect"});
  compareRoot.append(text("h3","Version history"),field("Restore or branch from version",versionSelect),field("Compare with version",compareSelect));
  const compareButton=button("Compare versions",compareVersions,"aw-btn");
  const branchButton=button("Explore this rendered version",branchFromRender,"aw-btn primary",true);
  compareRoot.append(el("div",{className:"aw-row"},[compareButton,branchButton]));
  const comparisonResult=text("div","","aw-status");
  compareRoot.append(comparisonResult);

  function setConnected(token) {
    if(typeof token!=="string"||token.trim().length<12) return;
    accessToken=token.trim();
    workspace.classList.remove("aw-hidden");
    connection.textContent="Connected in this page session. The access token is held in memory only.";
    status("Session connected. Loading your saved appearances…");
    loadLooks();
  }
  window.addEventListener("cirvanna:session-ready",event=>{
    setConnected(event.detail && event.detail.accessToken);
  });
  window.addEventListener("cirvanna:appearance-add-product",event=>{
    const product=event.detail||{};
    if(!accessToken) return status("Connect a signed-in Cirvanna account before adding a Marketplace product.","error");
    if(typeof product.productId!=="string"||!/^[A-Za-z0-9][A-Za-z0-9._:@-]{1,159}$/.test(product.productId)) {
      return status("The product did not include a valid canonical Catalog ID.","error");
    }
    componentSelect.value=product.component||"garment";
    actionSelect.value="apply";
    refKind.value=product.referenceKind||"catalog_product";
    refId.value=product.productId;
    description.value=String(product.productName||"Marketplace product").slice(0,500);
    root.scrollIntoView({behavior:"smooth",block:"start"});
    status("CAL-approved product loaded into the edit form. Choose a saved appearance and explicitly save the component edit.");
  });
  window.addEventListener("cirvanna:appearance-add-wardrobe-look",event=>{
    const look=event.detail||{};
    if(!accessToken) return status("Connect your Cirvanna account before sending a PNELLY look to Appearance.","error");
    const items=Array.isArray(look.items)?look.items.filter(item=>item&&typeof item.display_name==="string"):[];
    if(!items.length) return status("The PNELLY look contains no active wardrobe pieces to reference.","error");
    componentSelect.value="garment";
    actionSelect.value="apply";
    const firstId=items.find(item=>typeof item.item_id==="string"&&/^[A-Za-z0-9][A-Za-z0-9._:@-]{1,159}$/.test(item.item_id));
    refKind.value=firstId?"wardrobe_item":"";
    refId.value=firstId?firstId.item_id:"";
    description.value=("PNELLY "+String(look.role||"wardrobe look")+": "+items.map(item=>item.display_name).join(", ")).slice(0,500);
    root.scrollIntoView({behavior:"smooth",block:"start"});
    status("PNELLY's wardrobe look is ready as an editable garment plan. Review and save it to a selected appearance.");
  });

  async function loadLooks() {
    if(!accessToken) return;
    try {
      const data=await api(API.looks);
      if(!Array.isArray(data.looks)) throw new Error("APPEARANCE_LOOK_LIST_INVALID");
      looks=data.looks;
      renderLooks();
      status(looks.length+" saved appearance(s) found. Expired looks remain visible until you re-consent or delete them.","good");
    } catch(error) { status(error.message||"Could not load saved appearances.","error"); }
  }

  function renderLooks() {
    listRoot.replaceChildren();
    if(!looks.length) {
      listRoot.append(text("div","No saved appearances yet. Create one from a private source photo or an existing persistent Twin.","aw-muted"));
      return;
    }
    for(const summary of looks) {
      const meta=el("div",{className:"aw-look-meta"});
      meta.append(text("strong",summary.look_id),text("div",(summary.base_kind||"appearance")+" · version "+summary.version),
        text("div",summary.consent_required?"Consent required to reopen":"Updated "+new Date(summary.updated_at).toLocaleString()));
      const controls=el("div",{className:"aw-row"});
      controls.append(button(summary.consent_required?"Re-consent / open":"Open",()=>openLook(summary.look_id),"aw-btn"));
      listRoot.append(el("div",{className:"aw-look"},[meta,controls]));
    }
  }

  async function openLook(lookId) {
    const summary=looks.find(x=>x.look_id===lookId);
    try {
      if(summary?.consent_required) {
        const renewed=await renewConsent(summary);
        if(!renewed) return;
      }
      let detailData,versionData;
      try {
        [detailData,versionData]=await Promise.all([
          api(API.looks+"/"+encodeURIComponent(lookId)),
          api(API.looks+"/"+encodeURIComponent(lookId)+"/versions")
        ]);
      } catch(error) {
        if(error.status!==403||!summary) throw error;
        const renewed=await renewConsent({...summary,consent_required:true});
        if(!renewed) return;
        [detailData,versionData]=await Promise.all([
          api(API.looks+"/"+encodeURIComponent(lookId)),
          api(API.looks+"/"+encodeURIComponent(lookId)+"/versions")
        ]);
      }
      activeLook=detailData.look;
      versions=Array.isArray(versionData.versions)?versionData.versions:[];
      renderDetail();
      detail.classList.remove("aw-hidden");
      status("Opened "+lookId+". Edits are versioned and do not alter the chosen base.","good");
      detail.scrollIntoView({behavior:"smooth",block:"start"});
    } catch(error) { status(error.message||"Could not open this appearance look.","error"); }
  }

  function renewConsent(summary) {
    return new Promise(resolve=>{
      const source=summary.base_kind==="source_photo";
      const consentPanel=el("div",{className:"aw-status"});
      consentPanel.append(text("strong","This look's consent has expired or was withdrawn."));
      const session=check("I agree to keep this look and its edit history.","awRenewSession");
      const sourceCheck=check("I agree to keep the uploaded source photo in private storage.","awRenewSource");
      const processing=check("I agree to process this source photo for look instructions.","awRenewProcessing");
      const checks=el("div",{className:"aw-checks"},[session.wrap]);
      if(source) checks.append(sourceCheck.wrap,processing.wrap);
      const proceed=button("Grant fresh consent and continue",async()=>{
        if(!session.input.checked||(source&&(!sourceCheck.input.checked||!processing.input.checked))) {
          status("Check each permission you explicitly agree to before renewing.","error");
          return;
        }
        proceed.disabled=true;
        try {
          await api(API.renew,{method:"POST",body:{
            look_id:summary.look_id,
            accept_session_storage:true,
            accept_source_storage:source,
            accept_image_processing:source
          }});
          renewalPane.classList.add("aw-hidden");
          renewalPane.replaceChildren();
          await loadLooks();
          status("Consent renewed for this look. Reopening…","good");
          resolve(true);
        } catch(error) {
          status(error.message||"Consent renewal failed.","error");
          proceed.disabled=false;
        }
      },"aw-btn primary");
      const cancel=button("Cancel",()=>{
        renewalPane.classList.add("aw-hidden");
        renewalPane.replaceChildren();
        resolve(false);
      },"aw-btn");
      consentPanel.append(checks,el("div",{className:"aw-row"},[proceed,cancel]));
      renewalPane.replaceChildren(consentPanel);
      renewalPane.classList.remove("aw-hidden");
      detail.classList.remove("aw-hidden");
      detail.scrollIntoView({behavior:"smooth",block:"start"});
    });
  }

  function renderDetail() {
    operationRoot.replaceChildren();
    editForm.classList.remove("aw-hidden");
    compareRoot.classList.remove("aw-hidden");
    renewalPane.classList.add("aw-hidden");
    renewalPane.replaceChildren();
    detailMeta.textContent="Base: "+activeLook.base.kind+" · Version "+activeLook.version+
      (activeLook.base.twin_id?" · Twin "+activeLook.base.twin_id:"")+
      (activeLook.base.parent_look_id?" · Parent look "+activeLook.base.parent_look_id:"");
    const list=el("div");
    if(!activeLook.operations.length) list.append(text("div","No changes yet. This look remains at its chosen base appearance.","aw-muted"));
    for(const operation of activeLook.operations) {
      const item=el("div",{className:"aw-op"});
      item.append(text("span",operation.component,"aw-pill"),
        text("strong",operation.action.toUpperCase()+" · "+(operation.description||operation.reference_id||"No description")),
        text("div","Target regions: "+(operation.target_regions||[]).join(", ")));
      list.append(item);
    }
    operationRoot.append(list);
    versionSelect.replaceChildren();
    compareSelect.replaceChildren();
    for(const version of versions) {
      versionSelect.append(new Option("Version "+version.version+" · "+version.action,String(version.version)));
      compareSelect.append(new Option("Version "+version.version,String(version.version)));
    }
    const previous=versions.filter(v=>v.version<activeLook.version).pop();
    versionSelect.value=previous?String(previous.version):"";
    const output=versions.find(v=>v.version===activeLook.version);
    branchButton.disabled=!(output&&output.output_asset_id&&output.fidelity_assessment&&output.fidelity_assessment.disposition==="releasable");
    branchButton.textContent=branchButton.disabled?"Branch unavailable — no passing render":"Explore this rendered version";
    favoriteButton.textContent=activeLook.is_favorite?"Remove favourite":"Save favourite";
    undoButton.disabled=!versions.some(v=>v.version<activeLook.version);
  }

  async function refreshDetail() {
    if(!activeLook) return;
    const id=activeLook.look_id;
    const [detailData,versionData]=await Promise.all([
      api(API.looks+"/"+encodeURIComponent(id)),
      api(API.looks+"/"+encodeURIComponent(id)+"/versions")
    ]);
    activeLook=detailData.look;
    versions=Array.isArray(versionData.versions)?versionData.versions:[];
    renderDetail();
    await loadLooks();
  }

  async function createLook() {
    if(!accessToken) return status("Connect a signed-in account first.","error");
    const kind=baseSelect.value;
    if(!sessionConsent.input.checked) return status("Appearance-session storage consent is required to save a look.","error");
    if(kind==="source_photo") {
      const selected=file.files&&file.files[0];
      if(!selected) return status("Choose the source photo you want to work from.","error");
      if(selected.size<1||selected.size>MAX_SOURCE_BYTES) return status("The source photo must be between 1 byte and 10 MB.","error");
      if(!sourceConsent.input.checked||!processingConsent.input.checked) return status("Source-photo retention and image-processing permissions must be granted separately.","error");
    }
    if(kind==="virtual_twin"&&!twinId.value.trim()) return status("Enter an existing Virtual Twin ID.","error");
    createButton.disabled=true;
    const lookId=uuid();
    let consentId=null,assetId=null,lookCreated=false;
    try {
      const consent=await api(API.consents,{method:"POST",body:{
        look_id:lookId,base_kind:kind,accept_session_storage:true,
        accept_source_storage:kind==="source_photo",accept_image_processing:kind==="source_photo"
      }});
      consentId=consent.consent_id;
      let base;
      if(kind==="source_photo") {
        const form=new FormData();
        form.append("file",file.files[0]);
        const uploaded=await api(API.looks+"/"+encodeURIComponent(lookId)+"/source",{
          method:"POST",headers:{"X-Appearance-Consent-ID":consentId},body:form
        });
        assetId=uploaded.asset_id;
        base={kind:"source_photo",source_asset_ids:[assetId]};
      } else {
        base={kind:"virtual_twin",twin_id:twinId.value.trim()};
      }
      const created=await api(API.looks,{method:"POST",body:{
        look_id:lookId,subject_id:"browser-subject-is-replaced-by-bff",
        consent_id:consentId,idempotency_key:"create-"+uuid(),base,operations:[]
      }});
      lookCreated=true;
      activeLook=created.look;
      await refreshDetail();
      file.value="";
      twinId.value="";
      sessionConsent.input.checked=false;
      sourceConsent.input.checked=false;
      processingConsent.input.checked=false;
      status("Saved a new "+kind.replaceAll("_"," ")+" appearance look. No image was transformed.","good");
    } catch(error) {
      if(lookCreated) {
        status("The look was created, but refreshing its details failed: "+(error.message||"unknown error")+". Use Refresh to reopen it.","error");
        return;
      }
      const cleanup=[];
      if(assetId) {
        try {
          await api(API.looks+"/"+encodeURIComponent(lookId)+"/source/"+encodeURIComponent(assetId),{method:"DELETE"});
          cleanup.push("source asset deleted");
        } catch(_) { cleanup.push("source asset cleanup pending; retain look ID "+lookId); }
      }
      if(consentId) {
        try {
          await api(API.revoke,{method:"POST",body:{look_id:lookId,consent_id:consentId}});
          cleanup.push("consent revoked");
        } catch(_) { cleanup.push("consent revocation pending"); }
      }
      status((error.message||"Could not create appearance look")+(cleanup.length?" · "+cleanup.join(" · "):""),"error");
    } finally {
      createButton.disabled=false;
      await loadLooks();
    }
  }

  async function applyOperation() {
    if(!activeLook) return;
    const component=componentSelect.value, action=actionSelect.value;
    const referenceKind=refKind.value, referenceId=refId.value.trim(), summary=description.value.trim();
    if(action!=="remove"&&!referenceId&&!summary) return status("Describe the requested change or provide a reference ID.","error");
    if(referenceId&&!referenceKind) return status("Choose a reference type for the supplied reference ID.","error");
    const targetRegions=regionHint.value.split(",").map(x=>x.trim()).filter(Boolean);
    const operation={operation_id:uuid(),component,action,origin:"user_directed",preserve_unrequested_regions:true};
    if(summary) operation.description=summary;
    if(referenceId) { operation.reference_kind=referenceKind; operation.reference_id=referenceId; }
    if(targetRegions.length) operation.target_regions=targetRegions;
    applyButton.disabled=true;
    try {
      await api(API.looks+"/"+encodeURIComponent(activeLook.look_id)+"/operations",{
        method:"POST",body:{
          subject_id:"browser-subject-is-replaced-by-bff",
          expected_version:activeLook.version,command_id:"edit-"+uuid(),operation
        }
      });
      description.value="";refId.value="";regionHint.value="";
      await refreshDetail();
      status("Saved "+component+" edit as a new version. Unrequested components are preserved.","good");
    } catch(error) {
      status(error.message||"Could not save this appearance edit.","error");
      if(error.message.includes("APPEARANCE_VERSION_CONFLICT")) await refreshDetail().catch(()=>{});
    } finally { applyButton.disabled=false; }
  }

  async function resetLook() {
    if(!activeLook||!window.confirm("Reset this look to its selected original base? Earlier versions remain in its history.")) return;
    try {
      await api(API.looks+"/"+encodeURIComponent(activeLook.look_id)+"/reset",{
        method:"POST",body:{subject_id:"browser-subject-is-replaced-by-bff",expected_version:activeLook.version,command_id:"reset-"+uuid()}
      });
      await refreshDetail();
      status("A new reset version was saved. The original base remains unchanged.","good");
    } catch(error) { status(error.message||"Reset failed.","error"); }
  }
  async function undoLook() {
    if(!activeLook) return;
    const target=Number(versionSelect.value);
    if(!Number.isInteger(target)||target<1||target>=activeLook.version) return status("Choose an earlier version to restore.","error");
    try {
      await api(API.looks+"/"+encodeURIComponent(activeLook.look_id)+"/undo",{
        method:"POST",body:{subject_id:"browser-subject-is-replaced-by-bff",expected_version:activeLook.version,target_version:target,command_id:"undo-"+uuid()}
      });
      await refreshDetail();status("The chosen earlier composition is now a new version.","good");
    } catch(error) { status(error.message||"Undo failed.","error"); }
  }
  async function toggleFavorite() {
    if(!activeLook) return;
    try {
      await api(API.looks+"/"+encodeURIComponent(activeLook.look_id)+"/favorite",{
        method:"POST",body:{subject_id:"browser-subject-is-replaced-by-bff",is_favorite:!activeLook.is_favorite}
      });
      await refreshDetail();
    } catch(error) { status(error.message||"Could not update favourite.","error"); }
  }
  async function deleteLook() {
    if(!activeLook||!window.confirm("Delete this saved appearance, withdraw its consent and remove private media when no other active look uses it?")) return;
    try {
      const result=await api(API.looks+"/"+encodeURIComponent(activeLook.look_id),{
        method:"DELETE",body:{subject_id:"browser-subject-is-replaced-by-bff",expected_version:activeLook.version,command_id:"delete-"+uuid()}
      });
      const pending=result.deletion&&result.deletion.status!=="completed";
      activeLook=null;versions=[];detail.classList.add("aw-hidden");
      await loadLooks();
      status(pending?"Look deleted from your library. Private-media cleanup is pending and will be retried.":"Look deleted and its consent withdrawn; unshared private media cleanup completed.","good");
    } catch(error) { status(error.message||"Could not delete this look.","error"); }
  }
  async function revokeLookConsent() {
    if(!activeLook||!activeLook.consent_id||!window.confirm("Revoke this look's storage and processing permissions? The saved look will remain listed but cannot be opened until you grant fresh permissions.")) return;
    try {
      await api(API.revoke,{method:"POST",body:{look_id:activeLook.look_id,consent_id:activeLook.consent_id}});
      activeLook=null;versions=[];detail.classList.add("aw-hidden");await loadLooks();
      status("The exact look consent bundle was revoked. Other appearances are unaffected.","good");
    } catch(error) { status(error.message||"Consent revocation failed.","error"); }
  }
  async function compareVersions() {
    if(!activeLook) return;
    const from=Number(versionSelect.value),to=Number(compareSelect.value);
    if(!Number.isInteger(from)||!Number.isInteger(to)||from<1||to<1) return status("Choose two versions to compare.","error");
    try {
      const comparison=await api(API.looks+"/"+encodeURIComponent(activeLook.look_id)+"/compare?from_version="+from+"&to_version="+to);
      const changed=Array.isArray(comparison.changed_components)?comparison.changed_components:[];
      comparisonResult.textContent=changed.length?"Changed components: "+changed.join(", "):"No component differences between these versions.";
      status("Version comparison complete.","good");
    } catch(error) { status(error.message||"Could not compare versions.","error"); }
  }
  async function branchFromRender() {
    if(!activeLook) return;
    const current=versions.find(v=>v.version===activeLook.version);
    if(!current||!current.output_asset_id||!current.fidelity_assessment||current.fidelity_assessment.disposition!=="releasable") {
      return status("This version has no passing fidelity-gated render to branch from.","error");
    }
    if(!window.confirm("Create a new appearance based on this previously rendered result? The original photo is not duplicated into the new look.")) return;
    const newLookId=uuid();
    try {
      const consent=await api(API.consents,{method:"POST",body:{
        look_id:newLookId,base_kind:"previous_render",accept_session_storage:true,
        accept_source_storage:false,accept_image_processing:false
      }});
      await api(API.looks+"/"+encodeURIComponent(activeLook.look_id)+"/branch",{
        method:"POST",body:{
          subject_id:"browser-subject-is-replaced-by-bff",
          new_look_id:newLookId,consent_id:consent.consent_id,
          command_id:"branch-"+uuid(),parent_version:activeLook.version
        }
      });
      await loadLooks();status("Created a new branch from the prior fidelity-approved render.","good");
    } catch(error) { status(error.message||"Could not branch this appearance.","error"); }
  }

  if(window.CIRVANNA_APPEARANCE_SESSION&&window.CIRVANNA_APPEARANCE_SESSION.accessToken) {
    setConnected(window.CIRVANNA_APPEARANCE_SESSION.accessToken);
  }
})();