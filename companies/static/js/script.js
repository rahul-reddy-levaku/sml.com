// ========== DOM READY ========== //
document.addEventListener("DOMContentLoaded", function () {
    ensureSidebarClickCSS();     // keeps click-only sidebar behaviour
    ensureImagePreviewModal();   // make sure preview modal exists
    ensureFormLayoutCSS();       // no-scroll form + two-column/checkbox grid

    // ===== PASSWORD EYE: set up + hard guards (Amazon/Flipkart-style resilience) =====
    addEyeCSSGuard();            // CSS guard so only FIRST toggle shows inside .pro-passwrap
    setupGlobalEyeToggles();     // delegated click handler
    wirePasswordEyes(document);  // ensure a single eye per field
    dedupePasswordEyes(document);// remove extras (prefer manual)
    reMaskPasswords(document);   // keep masked by default
    startEyeObserver();          // MutationObserver to re-dedupe if any script injects another eye later

    const toggleBtn  = document.getElementById("sidebar-toggle");
    const sidebar    = document.getElementById("sidebar");
    const adminLink  = document.getElementById("admin-login-toggle");
    const loginModal = document.getElementById("login-modal");

    let loginClickedOnce = false;

    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener("click", function () {
            sidebar.classList.toggle("collapsed");
            const content = document.querySelector(".admin-main-content");
            if (content) {
                content.style.marginLeft = sidebar.classList.contains("collapsed") ? "0" : "250px";
            }
        });
    }

    if (adminLink) {
        adminLink.addEventListener("click", function (e) {
            e.preventDefault();
            const currentText = (adminLink.textContent || "").trim().toLowerCase();
            if (!loginClickedOnce && currentText.includes("admin")) {
                adminLink.textContent = "Login";
                loginClickedOnce = true;
            } else {
                openLoginModal();
            }
        });
    }

    // enable actionable buttons/links regardless of server markup
    ensureEntityButtonsEnabled();
    // normalize buttons so router can always infer entity/id
    normalizeEntityButtons(document);

    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") closeLoginModal();
    });

    if (loginModal) {
        loginModal.addEventListener("click", function (e) {
            if (e.target === loginModal) closeLoginModal();
        });
    }

    const loginForm = document.querySelector('#admin-login-form');
    if (loginForm && !loginForm.dataset.boundAjaxHandler) {
        loginForm.dataset.boundAjaxHandler = "1";

        const u = document.getElementById("login-username");
        const p = document.getElementById("login-password");
        const errDiv = document.getElementById("login-error");
        const submitBtn = document.getElementById("login-submit");
        const updateSubmitState = () => {
            const ok = (u && u.value.trim().length > 0) && (p && p.value.trim().length > 0);
            if (submitBtn) ok ? submitBtn.removeAttribute("disabled") : submitBtn.setAttribute("disabled","disabled");
            if (document.activeElement === u || document.activeElement === p) {
                if (errDiv) { errDiv.hidden = true; errDiv.style.display = ""; errDiv.textContent = ""; }
            }
        };
        u && u.addEventListener("input", updateSubmitState);
        p && p.addEventListener("input", updateSubmitState);
        updateSubmitState();

        loginForm.addEventListener("submit", function (e) {
            e.preventDefault();
            const formData = new FormData(loginForm);

            fetch(loginForm.action, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfTokenSafe(),
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json'
                },
                body: formData,
                credentials: "include",
                redirect: "follow"
            })
            .then(async res => {
                const ct = (res.headers.get("content-type") || "").toLowerCase();

                if (res.redirected && !ct.includes("application/json")) {
                    showInlineLoginError("Invalid credentials."); return;
                }
                if (res.status === 401 || res.status === 400 || res.status === 403) {
                    showInlineLoginError("Invalid credentials."); return;
                }

                if (ct.includes("application/json")) {
                    const data = await res.json();
                    if (data.success) {
                        closeLoginModal();
                        window.location.href = data.redirect_url || "/dashboard/";
                        return;
                    }
                    if (data.require_otp) {
                        const otpBlock = document.getElementById("otp-block");
                        if (otpBlock) otpBlock.hidden = false;
                    }
                    showInlineLoginError(data.error || "Invalid credentials.");
                    return;
                }

                showInlineLoginError("Invalid credentials.");
            })
            .catch(() => showInlineLoginError("Network error. Please try again."));
        });
    }

    setupSidebarDropdownToggle();
    setupRoleSwitches();

    initializeDatePickers();
    setupPermissionSelectAll();
    formatDateFields();          // keeps dd/mm/yyyy on screen + masks
    addMasks();
    setupAadharTypeahead();
    initPhoneInputs();

    // bind save + live validation for current modal if present
    setupSaveButtonHandler();
    const formNow = document.getElementById("entity-form");
    const saveNow = document.getElementById("modal-save-btn");
    prepareFormValidation(formNow, saveNow);

    applyCheckboxGrid(document);
});

// ===== Auth failure → open modal ===== //
function handleAuthFailure(msg) {
  if (typeof openLoginModal === "function") openLoginModal();
  showInlineLoginError(msg || "Not authenticated.");
  try { console.warn("Auth required"); } catch(e){}
}

// ===== Helper: force-show login error reliably ===== //
function showInlineLoginError(msg) {
  const errDiv = document.getElementById("login-error");
  if (!errDiv) { alert(msg || "Invalid credentials."); return; }
  errDiv.textContent = msg || "Invalid credentials.";
  errDiv.hidden = false;
  errDiv.style.display = "block";
  errDiv.setAttribute("role", "alert");
  errDiv.setAttribute("aria-live", "assertive");
}

/* ================= PASSWORD / EYE TOGGLE ================= */

/* 1) HARD CSS GUARD: only FIRST toggle inside .pro-passwrap is ever visible.
      This survives late-injected extra eyes from other scripts/extensions. */
function addEyeCSSGuard(){
  if (document.getElementById("eye-guard-style")) return;
  const s = document.createElement("style");
  s.id = "eye-guard-style";
  s.textContent = `
    .pro-passwrap :is([data-toggle-pass], .eye-icon, .toggle-password, .js-eye, [data-toggle="password"]) {
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }
    .pro-passwrap :is([data-toggle-pass], .eye-icon, .toggle-password, .js-eye, [data-toggle="password"]):not(:first-of-type) {
      display: none !important;
      visibility: hidden !important;
      pointer-events: none !important;
    }
  `;
  document.head.appendChild(s);
}

/* 2) Mask any accidental text-type password inputs (on load or after fragments). */
function reMaskPasswords(scope=document){
  (scope || document)
    .querySelectorAll('input.password-input, input[type="text"].password-input, .pro-passwrap input[type="text"][autocomplete="new-password"], .pro-passwrap input[type="text"][type=password i]')
    .forEach(inp => { try { inp.type = 'password'; } catch(_){} });
}

/* 3) Delegated toggler. Works for all injected or server-rendered eyes. */
function setupGlobalEyeToggles() {
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".js-eye, [data-toggle='password'], .toggle-password, .eye-icon, [data-toggle-pass]");
    if (!btn) return;
    e.preventDefault();

    const wrap = btn.closest(".pro-passwrap") || btn.closest(".input-group") || btn.parentElement;
    let input = null;

    const selRaw = btn.getAttribute("data-target") || btn.getAttribute("aria-controls");
    if (selRaw) {
      const sel = selRaw.startsWith("#") ? selRaw : ("#" + selRaw.replace(/^#/, ""));
      input = document.querySelector(sel);
    }
    if (!input && wrap) {
      input = wrap.querySelector("input[type='password'], input[type='text'].password, input[type='text'][data-password], input.password-input");
    }
    if (!input) return;

    input.type = (input.type === "password" ? "text" : "password");

    btn.classList.toggle("fa-eye");
    btn.classList.toggle("fa-eye-slash");
    btn.classList.toggle("ri-eye-line");
    btn.classList.toggle("ri-eye-off-line");

    btn.dataset.visible = String(input.type === "text");
  });
}

/* 4) Inject a single eye next to each password input if none exists nearby. */
function wirePasswordEyes(root=document){
  const scope = root || document;
  const TOGGLE_SEL = ".js-eye, [data-toggle='password'], .toggle-password, .eye-icon, [data-toggle-pass]";

  function isDecoyOrHidden(inp){
    // Explicit decoys / hidden hints
    if (inp.matches('[autocomplete="current-password"], [tabindex="-1"], [aria-hidden="true"]')) return true;
    // Zero-sized or display:none
    const style = window.getComputedStyle(inp);
    if (style.display === "none" || style.visibility === "hidden") return true;
    const r = inp.getBoundingClientRect();
    // Off-screen decoys (e.g., left:-9999px) or effectively invisible
    if (r.width <= 1 && r.height <= 1) return true;
    if (r.right < 0 || r.bottom < 0 || r.top > (window.innerHeight || 0) || r.left > (window.innerWidth || 0)) return true;
    return false;
  }

  scope.querySelectorAll('input[type="password"]').forEach((inp)=>{
    if (inp.dataset.eyeWired === "1") return;
    if (isDecoyOrHidden(inp)) { inp.dataset.eyeWired = "1"; return; } // ← skip decoys/hidden

    // Find/ensure a stable wrapper
    let container =
      inp.closest('.pro-passwrap') ||
      inp.closest('.input-group') ||
      inp.closest('.form-group') ||
      inp.parentElement;

    if (!inp.closest('.pro-passwrap')) {
      const wrap = document.createElement("div");
      wrap.className = "pro-passwrap";
      inp.parentNode.insertBefore(wrap, inp);
      wrap.appendChild(inp);
      container = wrap;
    } else {
      container = inp.closest('.pro-passwrap');
    }

    // If a toggle already exists, don't add another
    if (container.querySelector(TOGGLE_SEL)) { inp.dataset.eyeWired = "1"; return; }

    if (!inp.id) inp.id = "pw_" + Math.random().toString(36).slice(2);

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "eye-icon";
    btn.setAttribute("aria-label", "Toggle password visibility");
    btn.setAttribute("aria-controls", "#" + inp.id);
    btn.dataset.visible = "false";
    btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7Z"></path><circle cx="12" cy="12" r="3"></circle></svg>';

    Object.assign(btn.style, {
      position: "absolute",
      right: "8px",
      top: "50%",
      transform: "translateY(-50%)",
      border: "none",
      background: "transparent",
      cursor: "pointer",
      padding: "4px",
      lineHeight: "1"
    });

    container.appendChild(btn);
    inp.dataset.eyeWired = "1";
  });

  dedupePasswordEyes(scope);
}


/* 5) Remove extra eye icons and keep exactly one per password input. */
function dedupePasswordEyes(root=document){
  const scope = root || document;
  const TOGGLE_SEL = ".js-eye, [data-toggle='password'], .toggle-password, .eye-icon, [data-toggle-pass]";

  scope.querySelectorAll('input[type="password"], input[type="text"].password, input[type="text"][data-password], input.password-input').forEach(inp=>{
    const container = inp.closest('.pro-passwrap') || inp.closest('.input-group') || inp.closest('.form-group') || inp.parentElement;
    if (!container) return;

    const toggles = Array.from(container.querySelectorAll(TOGGLE_SEL));
    if (toggles.length <= 1) return;

    let keep = toggles.find(b => b.matches('[data-toggle-pass]'))
            || toggles.find(b => b.previousElementSibling === inp || b.nextElementSibling === inp)
            || toggles[0];

    toggles.forEach(b => { if (b !== keep) b.remove(); });
  });

  // Kill any legacy outsiders not inside intended wrapper
  scope.querySelectorAll('.toggle-password, .password-eye, .show-pass').forEach(el=>{
    if (!el.closest('.pro-passwrap')) el.remove();
  });
}

/* 6) LIVE ENFORCER: if any other script injects a second eye later, clamp it. */
let _eyeObserverStarted = false;
function startEyeObserver(){
  if (_eyeObserverStarted) return;
  _eyeObserverStarted = true;

  const enforce = (node) => {
    // Only touch nodes that could contain password fields
    if (!node || !(node.querySelectorAll)) return;
    const scope = node.matches && (node.matches('input, .pro-passwrap, form, body') ? node : null) || node;
    wirePasswordEyes(scope);
    dedupePasswordEyes(scope);
    reMaskPasswords(scope);
  };

  const mo = new MutationObserver((mutations)=>{
    let touched = false;
    for (const m of mutations){
      if (m.type === "childList"){
        m.addedNodes.forEach(n=>{
          if (n.nodeType === 1 && (n.matches('input[type="password"], .pro-passwrap, form') || n.querySelector?.('input[type="password"], .pro-passwrap'))) {
            touched = true;
            enforce(n);
          }
        });
      } else if (m.type === "attributes"){
        const t = m.target;
        if (t && t.matches && t.matches('input[type="password"]')) {
          touched = true;
          enforce(t.closest('.pro-passwrap') || t.parentElement || document);
        }
      }
    }
    // As a safety net, occasionally sweep the whole document if many mutations
    if (touched === false && mutations.length > 10) {
      enforce(document);
    }
  });

  mo.observe(document.documentElement || document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["class", "type"]
  });

  // One final sweep post-load (handles late scripts)
  setTimeout(()=> { wirePasswordEyes(document); dedupePasswordEyes(document); }, 0);
}

/* ================= END PASSWORD / EYE ================= */

// ===== NEW helper: make sure the click-only CSS rule is present ===== //
function ensureSidebarClickCSS() {
    if (document.getElementById("force-sidebar-open-css")) return;
    const style = document.createElement("style");
    style.id = "force-sidebar-open-css";
    style.textContent = ".sidebar .dropdown.open > .dropdown-menu{display:block!important;}";
    document.head.appendChild(style);
}

// ===== NEW helper: no-scroll modal forms + two-column fields + side-by-side options ===== //
function ensureFormLayoutCSS() {
    if (document.getElementById("no-scroll-grid-form-css")) return;
    const style = document.createElement("style");
    style.id = "no-scroll-grid-form-css";
    style.textContent = `
      #entity-modal { align-items: flex-start; overflow-y: auto; }
      #entity-modal .modal-content{ max-height: none !important; }
      #entity-modal .modal-body   { max-height: none !important; overflow: visible !important; }

      #entity-modal .modal-body form {
        display: grid;
        grid-template-columns: repeat(2, minmax(260px, 1fr));
        gap: 12px 24px;
      }
      #entity-modal .modal-body form .form-group,
      #entity-modal .modal-body form .form-row,
      #entity-modal .modal-body form fieldset,
      #entity-modal .modal-body form .field,
      #entity-modal .modal-body form .input-group {
        break-inside: avoid;
        page-break-inside: avoid;
      }

      #entity-modal .checkbox-grid {
        display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: flex-start;
      }
      #entity-modal .checkbox-grid .form-check,
      #entity-modal .checkbox-grid label,
      #entity-modal .checkbox-grid .form-check-label {
        display: inline-flex; align-items: center; gap: 6px;
        width: calc(50% - 16px);
      }
      #entity-modal .modal-body form .form-check { display: inline-flex; align-items: center; gap: 6px; }

      .checkbox-grid { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: flex-start; }
      .checkbox-grid .form-check,
      .checkbox-grid label,
      .checkbox-grid .form-check-label {
        display: inline-flex; align-items: center; gap: 6px;
        width: calc(50% - 16px);
      }

      #entity-modal select[multiple] { min-height: 140px; }

      .invalid { outline:2px solid #e00 !important; background:#fff5f5; }
      .save-disabled{ opacity:.6; pointer-events:none; }

      @media (max-width: 768px) {
        #entity-modal .modal-body form { grid-template-columns: 1fr; }
        #entity-modal .checkbox-grid .form-check,
        #entity-modal .checkbox-grid label,
        #entity-modal .checkbox-grid .form-check-label,
        .checkbox-grid .form-check,
        .checkbox-grid label,
        .checkbox-grid .form-check-label { width: 100%; }
      }
    `;
    document.head.appendChild(style);
}

/* intercept <a class="image-link"> so we open the preview instantly */
document.body.addEventListener("click", function (e) {
    const link = e.target.closest(".image-link");
    if (!link) return;
    e.preventDefault();

    let src = link.getAttribute("href") || "";
    if (src && !src.startsWith("/") && !src.startsWith("http")) src = "/media/" + src;

    const meta = {
        code:   link.dataset.code   || "",
        name:   link.dataset.name   || "",
        status: link.dataset.status || ""
    };

    const modal = document.getElementById("image-preview-modal");
    const img   = document.getElementById("image-preview");
    const info  = document.getElementById("image-meta-fields");

    if (img)  img.src = src;
    if (info) {
        const out = [];
        if (meta.code)   out.push(`<p><strong>Code:</strong> ${meta.code}</p>`);
        if (meta.name)   out.push(`<p><strong>Name:</strong> ${meta.name}</p>`);
        if (meta.status) out.push(`<p><strong>Status:</strong> ${meta.status}</p>`);
        info.innerHTML = out.join("");
    }
    if (modal) modal.style.display = "flex";
});

// ===== ensure the preview modal HTML exists ===== //
function ensureImagePreviewModal() {
    if (document.getElementById("image-preview-modal")) return;
    const modal = document.createElement("div");
    modal.id = "image-preview-modal";
    modal.className = "modal";
    modal.style.display = "none";
    modal.innerHTML = `
      <div class="modal-content image-modal">
        <div class="modal-header d-flex justify-content-between align-items-center mb-2">
          <h5 class="modal-title">Image Preview</h5>
          <button type="button" class="close-btn" onclick="closeImageModal()">&times;</button>
        </div>
        <div class="modal-body">
          <img id="image-preview" src="" alt="Preview"
               style="max-width:100%;max-height:400px;display:block;margin:0 auto 20px;">
          <div id="image-meta-fields"></div>
          <div class="d-flex justify-content-end mt-3">
            <button class="btn btn-secondary" onclick="closeImageModal()">Close</button>
          </div>
        </div>
      </div>`;
    document.body.appendChild(modal);
}

// ===== Helpers ===== //
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";");
        for (let cookie of cookies) {
            cookie = cookie.trim();
            if (cookie.startsWith(name + "=")) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// robust CSRF getter (works with form/meta; falls back to cookie if readable)
function getCsrfTokenSafe() {
    const el =
      document.querySelector('#entity-form input[name="csrfmiddlewaretoken"]') ||
      document.querySelector('form input[name="csrfmiddlewaretoken"]') ||
      document.querySelector('input[name="csrfmiddlewaretoken"]') ||
      document.querySelector('meta[name="csrf-token"]');
    if (el) return el.content || el.value || '';
    return getCookie('csrftoken') || '';
}

function getCurrentRole(){
    try { return (document.body && document.body.dataset && (document.body.dataset.role || "")).toLowerCase(); }
    catch(e){ return ""; }
}

// ===== Flatpickr Setup ===== //
function initializeDatePickers() {
    if (typeof flatpickr !== "undefined") {
        flatpickr(".date-field", { dateFormat: "d/m/Y", allowInput: true, altInput: false });
    }
}

/* === dd/mm/yyyy helpers (mask + validity) === */
function isValidDateDDMMYYYY(s){
  if (!/^\d{2}\/\d{2}\/\d{4}$/.test(s)) return false;
  const [d,m,y] = s.split('/').map(Number);
  if (y < 1900 || y > 9999) return false;
  if (m < 1 || m > 12) return false;
  const dim = new Date(y, m, 0).getDate();
  return d >= 1 && d <= dim;
}
function attachDateMask(el){
  if (!el || el.dataset.maskBound) return;
  el.dataset.maskBound = "1";
  el.setAttribute("maxlength","10");
  el.setAttribute("inputmode","numeric");
  el.addEventListener("input", (e)=>{
    let v = e.target.value.replace(/[^\d]/g,'').slice(0,8);
    if (v.length >= 5) v = v.slice(0,2)+"/"+v.slice(2,4)+"/"+v.slice(4);
    else if (v.length >= 3) v = v.slice(0,2)+"/"+v.slice(2);
    e.target.value = v;
    if (v.length === 10 && !isValidDateDDMMYYYY(v)) {
      e.target.setCustomValidity("Enter date as dd/mm/yyyy");
    } else {
      e.target.setCustomValidity("");
    }
    const form = e.target.form;
    if (form) {
      const saveBtn = document.getElementById("modal-save-btn");
      recomputeSaveEnabled(form, saveBtn);
    }
  });
  el.addEventListener("blur", (e)=>{
    const v = (e.target.value || "").trim();
    if (v && !isValidDateDDMMYYYY(v)) {
      e.target.setCustomValidity("Enter date as dd/mm/yyyy");
    } else {
      e.target.setCustomValidity("");
    }
  });
}

/* === make all date inputs type=text + mask + pattern without changing UI === */
function formatDateFields() {
    const sel = [
      "input.date-field",
      'input[placeholder="dd/mm/yyyy"]',
      'input[placeholder="DD/MM/YYYY"]',
      "input[data-type='date']",
      "input[name*='date']",
      "input[name*='dob']"
    ].join(",");

    document.querySelectorAll(sel).forEach(input => {
        if (input.value && input.value.includes("-") && /^\d{4}-\d{2}-\d{2}$/.test(input.value)) {
            const [yyyy, mm, dd] = input.value.split("-");
            input.value = `${dd}/${mm}/${yyyy}`;
        }
        input.pattern = "\\d{2}/\\d{2}/\\d{4}";
        input.placeholder = "dd/mm/yyyy";
        input.type = "text";
        attachDateMask(input);
        input.addEventListener("input", ()=> input.setCustomValidity(""));
    });
}

/* ===== Phone & Aadhaar live masks ===== */
function addMasks() {
    document.querySelectorAll('input[name="phone"]').forEach(el => {
        el.addEventListener('input', () => {
            el.value = el.value.replace(/\D/g,'').slice(0,10);
        });
    });
    document.querySelectorAll('input[name="aadhar"], #id_aadhar_number').forEach(el => {
        el.addEventListener('input', () => {
            const v = el.value.replace(/\D/g,'').slice(0,12);
            el.value = v.replace(/(\d{4})(?=\d)/g, "$1 ").trim();
        });
    });
}

/* ===== intl-tel-input initialiser ===== */
function initPhoneInputs() {
    if (typeof window.intlTelInput === "undefined") return;
    document.querySelectorAll('input[name="phone"]').forEach(inp => {
        if (inp.dataset.itiAttached) return;
        window.intlTelInput(inp, {
            separateDialCode: true,
            initialCountry: "in",
            preferredCountries: ["in","us","ae","gb"]
        });
        inp.dataset.itiAttached = "1";
        inp.addEventListener("input", () => {
            inp.value = inp.value.replace(/\D/g,'').slice(0,10);
        });
    });
}

/* ===== Client-joining Aadhaar type-ahead ===== */
function setupAadharTypeahead() {
    const aadharInput = document.getElementById('search-aadhar');
    if (!aadharInput) return;
    aadharInput.addEventListener('keyup', function () {
        const q = this.value.replace(/\D/g,'').slice(0,12);
        const tgt = document.getElementById('aadhar-results');
        if (q.length < 2) { if (tgt) tgt.innerHTML = ""; return; }
        fetch(`/search/client/aadhar/?q=${q}`, {
            headers: { "X-Requested-With": "XMLHttpRequest", "Accept": "application/json" },
            credentials: "include"
        })
        .then(r => r.json())
        .then(list => {
            if (!tgt) return;
            tgt.innerHTML = list.map(
              c => `<li data-id="${c.id}" onclick="loadClient(${c.id})">${c.aadhar} – ${c.name}</li>`
            ).join('');
        })
        .catch(err => console.error("Aadhaar search error:", err));
    });
}

/* Dummy stub */
function loadClient(id){ console.log("loadClient stub", id); }

// Prevent multiple Aadhar listeners
let _aadharListenerAdded = false;
function formatAadharInput() {
    if (_aadharListenerAdded) return;
    _aadharListenerAdded = true;
    document.addEventListener("input", function (e) {
        const input = e.target;
        if (input && input.id === "id_aadhar_number") {
            let raw = input.value.replace(/\D/g, "").slice(0, 12);
            input.value = raw.replace(/(.{4})(?=.)/g, "$1 ").trim();
        }
    });
}

function setupPermissionSelectAll() {
    document.querySelectorAll('.check-all').forEach(selectAllCheckbox => {
        const group = selectAllCheckbox.dataset.group;
        const groupCheckboxes = document.querySelectorAll(`.form-check-input.${group}`);

        selectAllCheckbox.addEventListener('change', function () {
            groupCheckboxes.forEach(cb => cb.checked = this.checked);
        });

        groupCheckboxes.forEach(cb => {
            cb.addEventListener('change', function () {
                const allChecked = Array.from(groupCheckboxes).every(c => c.checked);
                selectAllCheckbox.checked = allChecked;
            });
        });
    });
}

// === Role-level auto-permission switches === //
function setupRoleSwitches() {
    const master = document.getElementById('role-master-switch');
    const staff  = document.getElementById('role-staff-switch');
    const report = document.getElementById('role-report-switch');
    if (!master || !staff || !report) return;
    const checkboxes = Array.from(document.querySelectorAll('.perm-checkbox'));
    const loanAppPerms   = checkboxes.filter(cb => cb.dataset.perm?.includes('loanapplication'));
    const fieldSchedPerm = checkboxes.filter(cb => cb.dataset.perm?.includes('fieldschedule'));
    const fieldRepPerm   = checkboxes.filter(cb => cb.dataset.perm?.includes('fieldreport'));
    const clearAll = () => {
        checkboxes.forEach(cb => { cb.checked = false; cb.disabled = false; });
    };
    master.addEventListener('change', () => {
        clearAll();
        if (master.checked) {
            checkboxes.forEach(cb => cb.checked = true);
            staff.checked = report.checked = false;
        }
    });
    staff.addEventListener('change', () => {
        clearAll();
        if (staff.checked) {
            loanAppPerms.forEach(cb => { cb.checked = true; cb.disabled = true; });
            master.checked = report.checked = false;
        }
    });
    report.addEventListener('change', () => {
        clearAll();
        if (report.checked) {
            [...fieldSchedPerm, ...fieldRepPerm].forEach(cb => { cb.checked = true; cb.disabled = true; });
            master.checked = staff.checked = false;
        }
    });
}

// === Sidebar dropdown click-toggle === //
function setupSidebarDropdownToggle() {
  const dropdowns = Array.from(document.querySelectorAll(".sidebar .dropdown"));
  dropdowns.forEach(dd => {
    const link = dd.querySelector(":scope > a");
    if (!link) return;
    link.addEventListener("click", e => {
      e.preventDefault();
      dropdowns.forEach(d => { if (d !== dd) d.classList.remove("open"); });
      dd.classList.toggle("open");
    });
  });
  document.addEventListener("click", e => {
    if (!e.target.closest(".sidebar")) {
      dropdowns.forEach(d => d.classList.remove("open"));
    }
  });
}

// === Entity path helper (robust) === //
function getEntityBase(entity) {
    if (entity) {
        const seg = String(entity).replace(/\s+/g, "").toLowerCase();
        return `/${encodeURIComponent(seg)}/`;
    }
    let p = window.location.pathname;
    if (!p.endsWith('/')) p += '/';
    return p;
}

// ===== Modal Skeleton Builder ===== //
function ensureModalSkeleton() {
    if (document.getElementById("entity-modal")) return;
    const modal = document.createElement("div");
    modal.id = "entity-modal";
    modal.className = "modal";
    modal.style.display = "none";
    modal.innerHTML = `
      <div class="modal-content">
        <div class="modal-header" style="margin-bottom:12px;">
          <h5 id="entity-modal-title" class="modal-title"></h5>
          <button type="button" class="close-btn" onclick="closeEntityModal()">&times;</button>
        </div>
        <div class="modal-body">
          <div id="form-errors" role="alert" aria-live="assertive"></div>
          <div id="entity-modal-body"></div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" onclick="closeEntityModal()">Close</button>
          <button id="modal-save-btn" class="btn btn-primary save-disabled" disabled>Save</button>
        </div>
      </div>`;
    document.body.appendChild(modal);
}

/* ===== Visibility and completeness checks ===== */
function isVisible(el){ return !!(el && (el.offsetParent || el.getClientRects().length)); }
function isGroupChecked(form, el){
  const type = (el.type||"").toLowerCase();
  if (type !== "checkbox" && type !== "radio") return true;
  const name = el.name;
  if (!name) return true;
  const group = form.querySelectorAll(`input[type="${type}"][name="${CSS.escape(name)}"]`);
  return Array.from(group).some(g => g.checked);
}
function areAllVisibleFieldsFilled(form){
  const fields = form.querySelectorAll("input, select, textarea");
  for (const el of fields){
    if (!isVisible(el) || el.disabled || el.type === "hidden") continue;
    if (el.dataset.optional === "true") continue;
    const type = (el.type || "").toLowerCase();
    if (type === "button" || type === "submit" ) continue;
    if (type === "checkbox" || type === "radio"){
      if (!isGroupChecked(form, el)) return false;
      continue;
    }
    const val = String(el.value || "").trim();
    if (!val) return false;
  }
  return true;
}
function allDatesValid(form){
  const dateSel = [
    "input.date-field",
    'input[placeholder="dd/mm/yyyy"]',
    'input[placeholder="DD/MM/YYYY"]',
    "input[data-type='date']",
    "input[name*='date']",
    "input[name*='dob']"
  ].join(",");
  const list = form.querySelectorAll(dateSel);
  for (const el of list){
    if (!isVisible(el) || el.disabled) continue;
    const v = String(el.value||"").trim();
    if (v.length !== 10 || !isValidDateDDMMYYYY(v)) return false;
  }
  return true;
}
function recomputeSaveEnabled(form, saveBtn){
  if (!form || !saveBtn) return;
  const enable = areAllVisibleFieldsFilled(form) && allDatesValid(form) && validateForm(form).valid;
  saveBtn.disabled = !enable;
  saveBtn.classList.toggle("save-disabled", !enable);
}

// ===== VALIDATION STATE (Enable/Disable Save) ===== //
function prepareFormValidation(form, saveBtn) {
  if (!form || !saveBtn) return;

  // attach masks to any date fields present now
  const dateSel = [
    "input.date-field",
    'input[placeholder="dd/mm/yyyy"]',
    'input[placeholder="DD/MM/YYYY"]',
    "input[data-type='date']",
    "input[name*='date']",
    "input[name*='dob']"
  ].join(",");
  form.querySelectorAll(dateSel).forEach(attachDateMask);

  const toggleSave = () => recomputeSaveEnabled(form, saveBtn);

  saveBtn.disabled = true;
  saveBtn.classList.add("save-disabled");

  const onChange = () => {
    clearInvalids(form);
    toggleSave();
  };

  form.querySelectorAll("input, select, textarea").forEach(el => {
    el.addEventListener("input", onChange);
    el.addEventListener("change", onChange);
    el.addEventListener("blur", onChange);
  });

  toggleSave();
}

function clearInvalids(root){
  root && root.querySelectorAll(".invalid, .is-invalid").forEach(x => x.classList.remove("invalid","is-invalid"));
  root && root.querySelectorAll(".invalid-feedback").forEach(x => { x.textContent=""; x.style.display="none"; });
}

function validateForm(form){
  const result = { valid: true, firstEl: null, msg: "" };
  const fields = form.querySelectorAll("input, select, textarea");
  for (const el of fields){
    if (el.closest("[hidden]") || el.type === "hidden" || el.disabled) continue;
    const required = el.hasAttribute("required") || el.dataset.required === "true" || el.getAttribute("aria-required")==="true";
    const val = String(el.value || "").trim();

    if (required && !val){
      mark(el, "This field is required.");
      return fail(el, "Please fill the required field.");
    }
    if (el.type === "email" && val){
      const ok = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val);
      if (!ok){ mark(el, "Invalid email."); return fail(el, "Invalid email address."); }
    }
    if ((el.classList.contains("date-field") || el.dataset.type === "date" || /date|dob/i.test(el.name||"")) && val){
      const ok = isValidDateDDMMYYYY(val);
      if (!ok){ mark(el, "Use dd/mm/yyyy."); return fail(el, "Date must be dd/mm/yyyy."); }
    }
    if (el.name && el.name.toLowerCase().includes("aadhar") && val){
      const ok = /^\d{4}\s\d{4}\s\d{4}$/.test(val);
      if (!ok){ mark(el, "Enter Aadhaar as 1234 5678 9012."); return fail(el, "Invalid Aadhaar format."); }
    }
  }
  return result;

  function mark(el){ el.classList.add("invalid"); }
  function fail(el, msg){ result.valid=false; result.firstEl=el; result.msg=msg; return result; }
}

function focusAndClear(el){
  if (!el) return;
  try { el.focus({ preventScroll:false }); } catch {}
  if ("select" in el) try { el.select(); } catch {}
  el.value = "";
  el.scrollIntoView({ block:"center", behavior:"smooth" });
}

// ===== Modal Save Logic ===== //
function setupSaveButtonHandler() {
    const saveBtn = document.getElementById("modal-save-btn");
    if (!saveBtn || saveBtn.dataset.boundAjax === "1") return;
    saveBtn.dataset.boundAjax = "1";

    saveBtn.addEventListener("click", function (e) {
        e.preventDefault();
        const form = document.getElementById("entity-form");
        if (!form) return;

        clearFieldErrors(form);
        clearInvalids(form);

        const v = validateForm(form);
        if (!v.valid) {
            alert(v.msg || "Please correct highlighted fields.");
            focusAndClear(v.firstEl);
            return;
        }
        if (!areAllVisibleFieldsFilled(form) || !allDatesValid(form)) {
            alert("Please complete all fields and enter valid dates (dd/mm/yyyy).");
            return;
        }

        const url = form.action;
        const formData = new FormData(form);
        const errorDiv = ensureFormErrorBox();
        if (errorDiv) errorDiv.innerHTML = "";

        const dateSel = [
          "input.date-field",
          'input[placeholder="dd/mm/yyyy"]',
          'input[placeholder="DD/MM/YYYY"]',
          "input[data-type='date']",
          "input[name*='date']",
          "input[name*='dob']"
        ].join(",");
        form.querySelectorAll(dateSel).forEach(inp=>{
          const m = String(inp.value||"").trim().match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
          if (m) formData.set(inp.name, `${m[3]}-${m[2]}-${m[1]}`);
        });

        saveBtn.disabled = true;
        saveBtn.classList.add("save-disabled");
        const prevTxt = saveBtn.textContent;
        saveBtn.textContent = "Saving...";

        fetch(url, {
            method: "POST",
            headers: {
                "X-CSRFToken": getCsrfTokenSafe(),
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json,text/html"
            },
            body: formData,
            credentials: "include",
            redirect: "follow"
        })
        .then(async (res) => {
            const ct = (res.headers.get("content-type") || "").toLowerCase();
            if (res.status === 401 || res.status === 403 || res.redirected) { handleAuthFailure("Not authenticated."); return; }

            if (ct.includes("application/json")) {
                const data = await res.json();
                if (data.success) {
                    closeEntityModal();
                    location.reload();
                    return;
                }
                if (data.errors) {
                    const [field, msgs] = Object.entries(data.errors)[0] || [];
                    const msg = Array.isArray(msgs) ? msgs[0] : String(msgs || "Fix errors.");
                    showFormErrors(data.errors);
                    alert(msg || "Please fix the highlighted field.");
                    const errEl = locateField(document.getElementById("entity-form"), field);
                    if (errEl) { errEl.classList.add("invalid"); focusAndClear(errEl); }
                    return;
                }
                if (data.html) {
                    replaceModalWithHTML(data.html);
                    const f2 = document.getElementById("entity-form");
                    const b2 = document.getElementById("modal-save-btn");
                    prepareFormValidation(f2, b2);
                    wirePasswordEyes(document.getElementById("entity-modal"));
                    dedupePasswordEyes(document.getElementById("entity-modal"));
                    reMaskPasswords(document.getElementById("entity-modal"));
                    return;
                }
                alert("Validation failed.");
                return;
            }

            const text = await res.text().catch(()=> "");
            if (text && /id=["']entity-modal["']/.test(text)) {
                replaceModalWithHTML(text);
                const f2 = document.getElementById("entity-form");
                const b2 = document.getElementById("modal-save-btn");
                prepareFormValidation(f2, b2);
                wirePasswordEyes(document.getElementById("entity-modal"));
                dedupePasswordEyes(document.getElementById("entity-modal"));
                reMaskPasswords(document.getElementById("entity-modal"));
                return;
            }
            alert("Server returned unexpected response. Reloading...");
            location.reload();
        })
        .catch(err => {
            console.error("Submission failed:", err);
            alert("Submission failed. Check console.");
        })
        .finally(() => {
            saveBtn.disabled = false;
            saveBtn.classList.remove("save-disabled");
            saveBtn.textContent = prevTxt || "Save";
        });
    });
}

function ensureFormErrorBox() {
    let box = document.getElementById("form-errors");
    if (!box) {
        const modalBody = document.querySelector("#entity-modal .modal-body");
        if (modalBody) {
            box = document.createElement("div");
            box.id = "form-errors";
            box.setAttribute("role", "alert");
            box.setAttribute("aria-live", "assertive");
            modalBody.prepend(box);
        }
    }
    return box;
}

function showFormErrors(errors) {
    const errorDiv = ensureFormErrorBox();
    if (errorDiv) errorDiv.innerHTML = "";
    for (let field in errors) {
        const msgs = Array.isArray(errors[field]) ? errors[field].join(", ") : errors[field];
        if (errorDiv) errorDiv.innerHTML += `<p><strong>${field}:</strong> ${msgs}</p>`;
        markFieldInvalid(field, msgs);
    }
}

function markFieldInvalid(field, msg) {
    const form = document.getElementById("entity-form");
    if (!form) return;
    let input = locateField(form, field);
    if (!input) return;
    input.classList.add("is-invalid");
    let fb = input.closest(".form-group, .field, .input-group, div")?.querySelector(".invalid-feedback");
    if (!fb) {
        fb = document.createElement("div");
        fb.className = "invalid-feedback";
        input.after(fb);
    }
    fb.textContent = String(msg || "");
    fb.style.display = "block";
}

function clearFieldErrors(form) {
    form.querySelectorAll(".is-invalid").forEach(el => el.classList.remove("is-invalid"));
    form.querySelectorAll(".invalid-feedback").forEach(el => { el.textContent = ""; el.style.display = "none"; });
}

function focusFirstError(form) {
    const bad = form.querySelector(".is-invalid, .invalid");
    if (bad && typeof bad.focus === "function") {
        bad.focus();
        if ("select" in bad) try { bad.select(); } catch{}
        bad.value = "";
        bad.scrollIntoView({ block:"center", behavior:"smooth" });
    }
}

// Execute inline <script> tags inside a fragment
function executeInlineScripts(container) {
    if (!container) return;
    container.querySelectorAll("script").forEach(old => {
        const s = document.createElement("script");
        if (old.src) s.src = old.src; else s.textContent = old.textContent;
        document.body.appendChild(s);
        setTimeout(()=> s.remove(), 0);
    });
}

// Replace current modal with returned HTML
function replaceModalWithHTML(html) {
    const temp = document.createElement("div");
    temp.innerHTML = html.trim();
    const fresh = temp.querySelector("#entity-modal");
    if (!fresh) return;

    const existing = document.getElementById("entity-modal");
    if (existing) existing.remove();
    document.body.appendChild(fresh);
    fresh.style.display = "flex";

    ensureFormLayoutCSS();
    applyCheckboxGrid(fresh);
    initializeDatePickers();
    setupPermissionSelectAll();
    formatDateFields();
    addMasks();
    setupAadharTypeahead();
    formatAadharInput();
    initPhoneInputs();

    ensureFormErrorBox();
    executeInlineScripts(fresh);
    setupSaveButtonHandler();

    // wire validation + eye icons
    const f2 = document.getElementById("entity-form");
    const b2 = document.getElementById("modal-save-btn");
    prepareFormValidation(f2, b2);
    wirePasswordEyes(fresh);
    dedupePasswordEyes(fresh);
    reMaskPasswords(fresh);
}

// ===== Utility ===== //
function prettyName(entity) {
    return entity.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

/* ===== Auto-code filler ===== */
function fillAutoCode(entity) {
    let target = document.querySelector('#entity-form input[name="code"]');
    if (!target) {
        target =
            document.querySelector('#entity-form input[name="voucher_no"]') ||
            document.querySelector('#entity-form input[name="smtcode"]')   ||
            document.querySelector('#entity-form input[name="empcode"]')   ||
            document.querySelector('#entity-form input[name="staffcode"]') ||
            document.querySelector('#entity-form input[name="VCode"]');
    }
    if (!target || target.value) return;

    const entSeg = String(entity).replace(/\s+/g, "").toLowerCase();
    fetch("/next_code/", {
        method: "POST",
        headers: {
            "X-CSRFToken": getCsrfTokenSafe(),
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        },
        body: `entity=${encodeURIComponent(entSeg)}`,
        credentials: "include"
    })
    .then(r => r.json())
    .then(data => {
        if (data.code && target && !target.value) target.value = data.code;
    })
    .catch(err => console.error("code-fetch error:", err));
}

// ===== Centralized Modal Injection ===== //
function insertEntityModal(entity, html, mode, id) {
    const base = getEntityBase(entity);
    const temp = document.createElement("div");
    temp.innerHTML = html.trim();
    const returnedModal = temp.querySelector("#entity-modal");

    const existing = document.getElementById("entity-modal");
    if (existing) existing.remove();

    if (returnedModal) {
        document.body.appendChild(returnedModal);

        const titleEl = returnedModal.querySelector("#entity-modal-title");
        if (titleEl) titleEl.innerText = `${mode} ${prettyName(entity)}`;

        const form = returnedModal.querySelector("#entity-form");
        if (form) {
            form.dataset.entity = entity;
            if (mode === "Create") form.action = `${base}create/`;
            else if (mode === "Edit") form.action = `${base}update/${String(id).replace(/^:/, "")}/`;
        }

        ensureFormErrorBox();
        returnedModal.style.display = "flex";
        executeInlineScripts(returnedModal);
    } else {
        ensureModalSkeleton();
        const modal = document.getElementById("entity-modal");
        const title = document.getElementById("entity-modal-title");
        const bodyContainer = document.getElementById("entity-modal-body");
        if (!modal || !title || !bodyContainer) return;
        title.innerText = `${mode} ${prettyName(entity)}`;
        bodyContainer.innerHTML = html;
        modal.style.display = "flex";
        const form = document.getElementById("entity-form");
        if (form) {
            form.dataset.entity = entity;
            if (mode === "Create") form.action = `${base}create/`;
            else if (mode === "Edit") form.action = `${base}update/${String(id).replace(/^:/, "")}/`;
            if (mode === "Create") {
                const today = new Date();
                const formatted = `${String(today.getDate()).padStart(2, "0")}/${String(today.getMonth() + 1).padStart(2, "0")}/${today.getFullYear()}`;
                form.querySelectorAll("input.date-field").forEach(input => { if (!input.value) input.value = formatted; });
            }
        }
    }

    const modalToShow = document.getElementById("entity-modal");
    if (modalToShow) modalToShow.style.display = "flex";

    ensureFormLayoutCSS();
    applyCheckboxGrid(document.getElementById("entity-modal") || document);

    initializeDatePickers();
    setupPermissionSelectAll();
    formatDateFields();
    addMasks();
    setupAadharTypeahead();
    formatAadharInput();
    initPhoneInputs();
    fillAutoCode(entity);

    ensureFormErrorBox();
    setupSaveButtonHandler();
    setupRoleSwitches();

    // live validation + eye buttons for this form instance
    const f3 = document.getElementById("entity-form");
    const b3 = document.getElementById("modal-save-btn");
    prepareFormValidation(f3, b3);
    wirePasswordEyes(document.getElementById("entity-modal"));
    dedupePasswordEyes(document.getElementById("entity-modal"));
    reMaskPasswords(document.getElementById("entity-modal"));
}

// ===== Open / Edit Entity ===== //
function isUserPermEntity(ent) {
    return /^userpermissions?$/i.test(String(ent || ""));
}

function openEntityModal(entityOrEvent) {
    let entity;
    if (typeof entityOrEvent === "string") {
        entity = entityOrEvent;
    } else if (entityOrEvent && entityOrEvent.currentTarget) {
        const el = entityOrEvent.currentTarget;
        entity = getEntityFromElement(el) || el.dataset.entity || el.getAttribute("data-entity");
    }
    if (!entity) { console.error("No entity provided to openEntityModal"); return; }

    // Allow modal on the UserPermission list page, otherwise redirect there.
    if (isUserPermEntity(entity)) {
        const onUserPermPage = /\/userpermissions?\/?$/i.test(window.location.pathname);
        if (!onUserPermPage) { window.location.href = "/UserPermission/"; return; }
        // fall through to open the modal normally on /UserPermission/
    }

    const base = getEntityBase(entity);
    const url = `${base}get/`;
    fetch(url, {
        headers: { "X-Requested-With": "XMLHttpRequest", "Accept": "application/json,text/html" },
        credentials: "include",
        cache: "no-store",
        redirect: "follow"
    })
    .then(async res => {
        if (res.status === 401 || res.status === 403 || res.redirected) { handleAuthFailure("Not authenticated."); return; }
        const ct = res.headers.get("content-type") || "";
        let html;

        if (ct.includes("application/json")) {
            const data = await res.json();
            if (!res.ok || !data.success) { alert(data.error || `Error ${res.status}`); return; }
            if (data.warning) console.warn(data.warning);
            html = data.html || "";
        } else {
            const text = await res.text();
            if (res.status === 404) { alert("Form endpoint not found."); return; }
            html = text;
        }

        if (!html) { alert("Empty form response."); return; }
        insertEntityModal(entity, html, "Create");
    })
    .catch(err => { console.error("Load create form error:", err); alert("Failed to load create form."); });
}

function editEntity(entity, id) {
    if (!entity || !id) { console.error("editEntity requires entity and id"); return; }
    if (isUserPermEntity(entity)) { alert("Use the User Permissions page to manage permissions."); return; }

    id = String(id).replace(/^:/, "");
    const base = getEntityBase(entity);
    const url = `${base}get/${id}/`;
    fetch(url, { headers:{ "X-Requested-With":"XMLHttpRequest", "Accept": "application/json,text/html" }, credentials:"include", cache:"no-store", redirect:"follow" })
    .then(async res => {
        if (res.status === 401 || res.status === 403 || res.redirected) { handleAuthFailure("Not authenticated."); return; }
        const ct = res.headers.get("content-type") || "";
        let html;

        if (ct.includes("application/json")) {
            const data = await res.json();
            if (!res.ok || !data.success) { alert(data.error || `Error ${res.status}`); return; }
            if (data.warning) console.warn(data.warning);
            html = data.html || "";
        } else {
            const text = await res.text();
            if (res.status === 404) { alert("Edit form endpoint not found."); return; }
            html = text;
        }

        if (!html) { alert("Empty form response."); return; }
        insertEntityModal(entity, html, "Edit", id);
    })
    .catch(err => { console.error("Edit load error:", err); alert("Failed to load data."); });
}

function closeEntityModal() {
    const modal = document.getElementById("entity-modal");
    if (modal) modal.style.display = "none";
}

// ===== Delete ===== //
function deleteEntity(entity, id) {
    if (!confirm("Are you sure you want to delete this item?")) return;

    if (getCurrentRole() === "master") { alert("Delete is disabled for Master role."); return; }
    if (isUserPermEntity(entity)) { alert("This is a settings page with no table. Use the User Permissions UI."); return; }

    id = String(id).replace(/^:/, "");
    const entSeg = String(entity).replace(/\s+/g, "").toLowerCase();
    const url = `/${encodeURIComponent(entSeg)}/delete/${encodeURIComponent(id)}/`;

    fetch(url, {
        method: "POST",
        headers: { "X-CSRFToken": getCsrfTokenSafe(), "X-Requested-With": "XMLHttpRequest", "Accept": "application/json" },
        credentials: "include",
        redirect: "follow"
    })
    .then(async res => {
        const ct = (res.headers.get("content-type") || "").toLowerCase();
        if (res.status === 401) { handleAuthFailure("Not authenticated."); return; }
        if (res.status === 403 || res.redirected) { handleAuthFailure("Not authenticated."); return; }

        if (ct.includes("application/json")) {
            const data = await res.json();
            if (data.success) { location.reload(); }
            else {
                const msg = String(data.error || "").toLowerCase();
                const tableMissing =
                  /no such table|table .* does not exist|relation .* does not exist|undefinedtable|table .* not present/i.test(msg);
                const limited = (entSeg === "userprofile" || entSeg === "hrpm");
                if (tableMissing && limited) {
                    alert("Table missing. Run migrations, then retry delete.");
                } else {
                    alert(data.error || "Delete failed.");
                }
            }
            return;
        }

        const t = await res.text().catch(() => "");
        if (res.status === 403 && /csrf|forgery/i.test(t)) {
            alert("CSRF validation failed or session expired. Refresh the page and try again.");
        } else {
            alert("Server returned unexpected response while deleting.");
            console.error("Delete non-JSON response:", t.slice(0, 500));
        }
    })
    .catch(err => { console.error("Delete error:", err); alert("Delete request failed. Check console for details."); });
}

/* ===== Fresh login modal state helper ===== */
function resetLoginModalState() {
    const u = document.getElementById("login-username");
    const p = document.getElementById("login-password");
    const otpBlock = document.getElementById("otp-block");
    const err = document.getElementById("login-error");
    const submitBtn = document.getElementById("login-submit");

    if (u) { u.value = ""; u.setAttribute("readonly","readonly"); }
    if (p) { p.value = ""; p.setAttribute("readonly","readonly"); }

    [u,p].forEach(el => {
        if (!el) return;
        const unlock = () => el.removeAttribute("readonly");
        ["focus","keydown","pointerdown"].forEach(ev =>
          el.addEventListener(ev, function handler(){ unlock(); el.removeEventListener(ev, handler); }, { once:true })
        );
    });

    if (otpBlock) otpBlock.hidden = true;
    if (err) { err.hidden = true; err.style.display = ""; err.textContent = ""; }

    if (submitBtn) submitBtn.setAttribute("disabled","disabled");
}

// ===== Login Modal ===== //
function openLoginModal() {
    const loginModal = document.getElementById("login-modal");
    if (loginModal) {
        resetLoginModalState();
        loginModal.classList.add("show");
        loginModal.style.display = "flex";

        // ensure single working eye in login form too
        wirePasswordEyes(loginModal);
        dedupePasswordEyes(loginModal);
        reMaskPasswords(loginModal);

        const u = document.getElementById("login-username");
        if (u) setTimeout(()=>u.focus(), 0);
    } else {
        alert("Not authenticated.");
    }
}
function closeLoginModal() {
    const loginModal = document.getElementById("login-modal");
    if (loginModal) {
        loginModal.classList.remove("show");
        loginModal.style.display = "none";
        resetLoginModalState();
    }
}

// ===== Image Preview ===== //
function openImageModal(id, entity, field) {
    ensureImagePreviewModal();
    const modal         = document.getElementById("image-preview-modal");
    const imageTag      = document.getElementById("image-preview");
    const metaContainer = document.getElementById("image-meta-fields");

    if (imageTag) imageTag.src = "";
    if (metaContainer) metaContainer.innerHTML = "";

    id = String(id).replace(/^:/, "");
    const base = getEntityBase(entity);
    const url = `${base}get/${id}/`;
    fetch(url, { headers:{ "X-Requested-With":"XMLHttpRequest", "Accept": "application/json" }, credentials:"include", cache:"no-store", redirect:"follow" })
    .then(async res => {
        if (res.status === 401 || res.status === 403 || res.redirected) { handleAuthFailure("Not authenticated."); return; }

        const ct = res.headers.get("content-type") || "";
        let data = {};
        if (ct.includes("application/json")) {
            data = await res.json();
        } else {
            const text = await res.text();
            data[field] = text.trim();
        }

        let img = data[field];
        if (img && typeof img === "object") img = img.url || img.path || "";
        if (!img) { alert("Image not available."); return; }
        if (!img.startsWith("/") && !img.startsWith("http")) img = `/media/${img}`;
        imageTag.src = img;

        const lines = [];
        if (data.code)   lines.push(`<p><strong>Code:</strong> ${data.code}</p>`);
        if (data.name)   lines.push(`<p><strong>Name:</strong> ${data.name}</p>`);
        if (data.status) lines.push(`<p><strong>Status:</strong> ${data.status}</p>`);
        metaContainer.innerHTML = lines.join("");
        modal.style.display = "flex";
    })
    .catch(err => { console.error("Image preview error:", err); alert("Failed to load image preview."); });
}

function closeImageModal() {
    const modal = document.getElementById("image-preview-modal");
    if (modal) modal.style.display = "none";
}

// === CREDIT BUREAU MODAL + CALL === //
function openCreditPullModal() {
  let modal = document.getElementById("credit-modal");
  if (modal) { modal.remove(); }
  modal = document.createElement("div");
  modal.id = "credit-modal";
  modal.className = "modal";
  modal.style.display = "flex";
  modal.innerHTML = `
    <div class="modal-content" style="max-width:520px;">
      <div class="modal-header d-flex justify-content-between align-items-center mb-2">
        <h5 class="modal-title">Credit Bureau Check</h5>
        <button type="button" class="close-btn" onclick="document.getElementById('credit-modal').remove()">&times;</button>
      </div>
      <div class="modal-body">
        <div class="mb-2"><input id="cb-name" class="form-control" placeholder="Full Name"></div>
        <div class="mb-2"><input id="cb-dob" class="form-control" placeholder="DOB dd/mm/yyyy"></div>
        <div class="mb-2"><input id="cb-pan" class="form-control" placeholder="PAN"></div>
        <div class="mb-2"><input id="cb-aadhar" class="form-control" placeholder="Aadhaar (0000 0000 0000)"></div>
        <div class="d-flex justify-content-end gap-2 mt-3">
          <button class="btn btn-secondary" onclick="document.getElementById('credit-modal').remove()">Close</button>
          <button class="btn btn-primary" id="cb-submit">Check</button>
        </div>
        <pre id="cb-result" class="mt-3" style="white-space:pre-wrap;max-height:260px;overflow:auto;"></pre>
      </div>
    </div>`;
  document.body.appendChild(modal);

  const aad = modal.querySelector("#cb-aadhar");
  aad && aad.addEventListener("input", () => {
    const v = aad.value.replace(/\D/g,'').slice(0,12);
    aad.value = v.replace(/(\d{4})(?=\d)/g, "$1 ").trim();
  });

  modal.querySelector("#cb-submit").addEventListener("click", submitCreditPull);
}

async function submitCreditPull() {
  const modal = document.getElementById("credit-modal");
  if (!modal) return;
  const payload = {
    name:   (modal.querySelector("#cb-name")?.value || "").trim(),
    dob:    (modal.querySelector("#cb-dob")?.value || "").trim(),
    pan:    (modal.querySelector("#cb-pan")?.value || "").trim(),
    aadhar: (modal.querySelector("#cb-aadhar")?.value || "").replace(/\s+/g,'')
  };
  const result = modal.querySelector("#cb-result");
  result.textContent = "Checking…";

  try {
    const res = await fetch("/api/credit-bureau/pull/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": getCsrfTokenSafe(),
        "Accept": "application/json"
      },
      credentials: "include",
      body: JSON.stringify(payload),
      redirect: "follow"
    });
    const ct = (res.headers.get("content-type") || "").toLowerCase();
    if (res.status === 401 || res.status === 403 || res.redirected) {
      handleAuthFailure("Not authenticated.");
      return;
    }
    if (!ct.includes("application/json")) {
      const txt = await res.text().catch(()=> "");
      result.textContent = "Unexpected server response.\n" + txt.slice(0,300);
      return;
    }
    const data = await res.json();
    result.textContent = JSON.stringify(data, null, 2);
  } catch (e) {
    console.error("credit pull error", e);
    result.textContent = "Network error. Please try again.";
  }
}

// === expose globally for inline handlers ===
window.openEntityModal  = openEntityModal;
window.editEntity       = editEntity;
window.deleteEntity     = deleteEntity;
window.closeEntityModal = closeEntityModal;
window.openImageModal   = openImageModal;
window.closeImageModal  = closeImageModal;
window.openCreditPullModal = openCreditPullModal;

/* ===== Detect checkbox/radio groups and make them side-by-side ===== */
function applyCheckboxGrid(root){
  try{
    const scope = root || document;
    const containers = new Set();
    scope.querySelectorAll('input[type="checkbox"], input[type="radio"], .perm-checkbox').forEach(inp=>{
      const c = inp.closest('.form-group') || inp.closest('fieldset') || (inp.closest('.form-check') && inp.closest('.form-check').parentElement) || inp.parentElement;
      if (c) containers.add(c);
    });
    containers.forEach(c => c.classList.add('checkbox-grid'));
  }catch(e){ console.warn("applyCheckboxGrid warning:", e); }
}

/* ===== Enable entity buttons regardless of markup ===== */
const ENTITY_BTN_SEL = "[data-open-entity], [data-edit-entity], [data-delete-entity], .btn-add, .btn-edit, .btn-delete, [id^='create-'][id$='-btn']";
function ensureEntityButtonsEnabled(){
  document.querySelectorAll(ENTITY_BTN_SEL).forEach(el => {
    el.removeAttribute("disabled");
    el.setAttribute("aria-disabled","false");
    el.classList.remove("disabled");
    el.style.pointerEvents = "";
    if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex","0");
    if (!el.hasAttribute("role")) el.setAttribute("role", el.tagName === "A" ? "link" : "button");
  });
}

/* ===== Parse entity/id from element, href, or id ===== */
function getEntityFromElement(el){
  if (!el) return "";
  let entity = el.dataset.openEntity || el.dataset.editEntity || el.dataset.deleteEntity || el.dataset.entity || el.getAttribute("data-entity") || "";
  if (entity) return entity;

  const idAttr = el.id || "";
  if (/^create-.+-btn$/i.test(idAttr)) {
    return idAttr.replace(/^create-/, "").replace(/-btn$/,"");
  }

  const href = el.getAttribute("href") || "";
  if (href) {
    const m = href.match(/^\/([^\/]+)\/(get|create|update|delete)(\/|$)/i);
    if (m) return m[1];
  }
  const wrap = el.closest("[data-entity]");
  if (wrap) return wrap.getAttribute("data-entity") || "";
  return "";
}
function getIdFromElement(el){
  if (!el) return "";
  let id =
    el.dataset.id ||
    el.getAttribute("data-id") ||
    (el.closest("[data-id]")?.getAttribute("data-id") || "");

  if (!id) {
    const href = el.getAttribute("href") || "";
    const m = href && href.match(/\/(update|get|delete)\/([^\/]+)\/?$/i);
    if (m) id = m[2];
  }
  return (id || "").replace(/^:/, "");
}

/* ===== Normalize buttons by stamping data-* so router is consistent ===== */
function normalizeEntityButtons(scope){
  (scope || document).querySelectorAll("a[href^='/'], button, .btn").forEach(el=>{
    const href = el.getAttribute && el.getAttribute("href");
    if (!href) return;

    const mAdd  = href.match(/^\/([^\/]+)\/get\/?$/i);
    const mEdit = href.match(/^\/([^\/]+)\/update\/([^\/]+)\/?$/i);
    const mDel  = href.match(/^\/([^\/]+)\/delete\/([^\/]+)\/?$/i);

    if (mAdd) {
      el.dataset.openEntity = el.dataset.openEntity || mAdd[1];
      el.dataset.entity = el.dataset.entity || mAdd[1];
      el.classList.add("btn-add");
    } else if (mEdit) {
      el.dataset.editEntity = el.dataset.editEntity || mEdit[1];
      el.dataset.entity = el.dataset.entity || mEdit[1];
      el.dataset.id = el.dataset.id || mEdit[2];
      el.classList.add("btn-edit");
    } else if (mDel) {
      el.dataset.deleteEntity = el.dataset.deleteEntity || mDel[1];
      el.dataset.entity = el.dataset.entity || mDel[1];
      el.dataset.id = el.dataset.id || mDel[2];
      el.classList.add("btn-delete");
    }
  });
}

/* ===== Keyboard activation for button-like elements ===== */
document.addEventListener("keydown", function(e){
  if (e.key !== "Enter" && e.key !== " ") return;
  const t = e.target;
  if (!t || !t.matches(ENTITY_BTN_SEL)) return;
  e.preventDefault();
  t.click();
});

/* === Unified delegated router for Add / Edit / Delete === */
document.addEventListener("click", function (e) {
  const t = e.target.closest(ENTITY_BTN_SEL);
  if (!t) return;

  let entity = getEntityFromElement(t);
  let id = getIdFromElement(t);

  if (!entity) return;

  e.preventDefault();

  if (t.matches("[data-open-entity], .btn-add, [id^='create-'][id$='-btn']")) {
    openEntityModal(entity);
  } else if (t.matches("[data-edit-entity], .btn-edit")) {
    if (!id) { console.warn("Edit clicked without id", t); return; }
    editEntity(entity, id);
  } else if (t.matches("[data-delete-entity], .btn-delete")) {
    if (!id) { console.warn("Delete clicked without id", t); return; }
    deleteEntity(entity, id);
  }
});

/* ===================== USERPROFILE BUTTON PATCH (scoped) ===================== */
(function fixUserProfileButtons(){
  const isUP = /(^|\/)userprofile(\/|$)/i.test(location.pathname) ||
               (/^userprofile$/i.test(document.body?.dataset?.entity || ""));
  if (!isUP) return;

  (function ensureUPCss(){
    if (document.getElementById('userprofile-button-unlock')) return;
    const s = document.createElement('style');
    s.id = 'userprofile-button-unlock';
    s.textContent = `
      a[href^="/userprofile/"], a[href^="/UserProfile/"] { pointer-events:auto !important; opacity:1 !important; }
      a[href^="/userprofile/"].disabled, a[href^="/UserProfile/"].disabled { pointer-events:auto !important; opacity:1 !important; }
      .up-force-pointer { pointer-events:auto !important; opacity:1 !important; }
    `;
    document.head.appendChild(s);
  })();

  function enable(el){
    if (!el) return;
    el.removeAttribute('disabled');
    el.setAttribute('aria-disabled','false');
    el.classList.remove('disabled');
    el.classList.add('up-force-pointer');
    el.style.pointerEvents = 'auto';
    if (!el.hasAttribute('tabindex')) el.tabIndex = 0;
    if (!el.hasAttribute('role')) el.setAttribute('role', el.tagName === 'A' ? 'link' : 'button');
  }

  function idFromHref(href, op){
    const m = String(href||"").match(new RegExp(`${op}/([^/]+)/?$`, "i"));
    return m ? m[1].replace(/^:/,'') : "";
  }

  function idFromRow(el){
    const tr = el.closest('tr');
    if (!tr) return "";
    const pk =
      tr.dataset.id || tr.dataset.pk ||
      tr.getAttribute('data-id') || tr.getAttribute('data-pk') || "";
    if (pk) return pk.replace(/^:/,'');
    const cell = tr.querySelector('td,th');
    const v = (cell?.textContent || "").trim();
    return /^\d+$/.test(v) ? v : "";
  }

  function bindAdd(){
    const nodes = new Set([
      ...document.querySelectorAll('a[href^="/userprofile/get"]'),
      ...document.querySelectorAll('a[href^="/UserProfile/get"]'),
      ...document.querySelectorAll('[data-open-entity="UserProfile"], [data-open-entity="userprofile"]'),
      ...document.querySelectorAll('#create-UserProfile-btn, #create-userprofile-btn, #create-userprofile')
    ]);
    if (nodes.size === 0) {
      document.querySelectorAll('.grid-container .btn, .grid-header .btn, .page-actions .btn').forEach(b=>{
        if (/^add|create$/i.test((b.textContent||"").trim())) nodes.add(b);
      });
    }
    nodes.forEach(a=>{
      if (a.dataset.boundUserProfileAdd) return;
      enable(a);
      a.dataset.boundUserProfileAdd = "1";
      a.addEventListener('click', e=>{
        e.preventDefault(); e.stopPropagation();
        try { openEntityModal('UserProfile'); } catch(_) { console.error('openEntityModal missing'); }
      });
    });
  }

  function bindEdit(){
    const anchors = [
      ...document.querySelectorAll('a[href*="/userprofile/update/"]'),
      ...document.querySelectorAll('a[href*="/UserProfile/update/"]'),
      ...document.querySelectorAll('[data-edit-entity="UserProfile"], [data-edit-entity="userprofile"]')
    ];
    anchors.forEach(a=>{
      if (a.dataset.boundUserProfileEdit) return;
      enable(a);
      a.dataset.boundUserProfileEdit = "1";
      a.addEventListener('click', e=>{
        e.preventDefault(); e.stopPropagation();
        const id = idFromHref(a.getAttribute('href'), 'update') || idFromRow(a);
        if (!id) { console.warn('UserProfile edit id missing'); return; }
        try { editEntity('UserProfile', id); } catch(_) { console.error('editEntity missing'); }
      });
    });
  }

  function bindDelete(){
    const anchors = [
      ...document.querySelectorAll('a[href*="/userprofile/delete/"]'),
      ...document.querySelectorAll('a[href*="/UserProfile/delete/"]'),
      ...document.querySelectorAll('[data-delete-entity="UserProfile"], [data-delete-entity="userprofile"]')
    ];
    anchors.forEach(a=>{
      if (a.dataset.boundUserProfileDelete) return;
      enable(a);
      a.dataset.boundUserProfileDelete = "1";
      a.addEventListener('click', e=>{
        e.preventDefault(); e.stopPropagation();
        const id = idFromHref(a.getAttribute('href'), 'delete') || idFromRow(a);
        if (!id) { console.warn('UserProfile delete id missing'); return; }
        try { deleteEntity('UserProfile', id); } catch(_) { console.error('deleteEntity missing'); }
      });
    });
  }

  function bindAll(){ bindAdd(); bindEdit(); bindDelete(); }
  bindAll();

  const mo = new MutationObserver(() => bindAll());
  mo.observe(document.body, { childList:true, subtree:true });
})();

// ===== FIELD/FORM UTILITIES ===== //
function locateField(form, fieldName) {
  if (!fieldName) return null;
  let el = form.querySelector(`[name="${CSS.escape(fieldName)}"]`);
  if (!el) el = form.querySelector(`[name="${CSS.escape(fieldName)}[]"]`);
  if (!el) el = form.querySelector(`#id_${CSS.escape(fieldName)}`);
  if (!el) el = form.querySelector(`[id$="${CSS.escape(fieldName)}"]`);
  return el;
}
