// nano Agent console. Vanilla JS, no build step. SECURITY: all dynamic text is set with textContent only (no HTML string APIs).
(() => {
"use strict";
const $ = (s, el = document) => el.querySelector(s);
let S = {}, ME = {}, lang = "en", tab = "home", sub = {}, chatRole = "chat", viewSerial = 0;
const t = (k, v) => { let s = S[k] || k; if (v) for (const x in v) s = s.replace("{" + x + "}", v[x]); return s; };

function h(tag, props, ...kids) {
  const e = document.createElement(tag);
  for (const k in props || {}) {
    const v = props[k];
    if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "text") e.textContent = v; else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
}
function sv(tag, props = {}, ...kids) {
  const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(props)) e.setAttribute(k, String(v));
  for (const c of kids.flat()) if (c) e.append(c);
  return e;
}

// Clean geometric SVG icon set (no emojis).
const ICONS = {
  home: [["path", { d: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" }]],
  chat: [["path", { d: "M4 5h16v11H9l-5 4V5z" }]],
  manage: [["rect", { x: 4, y: 4, width: 16, height: 16, rx: 3 }], ["path", { d: "m8.5 12 2.5 2.5 4.5-5" }]],
  system: [["rect", { x: 3, y: 4, width: 18, height: 6, rx: 1.5 }], ["rect", { x: 3, y: 14, width: 18, height: 6, rx: 1.5 }], ["path", { d: "M7 7h.01M7 17h.01" }]],
  auto: [["circle", { cx: 12, cy: 12, r: 9 }], ["path", { d: "M12 7v5l3 2" }]],
  skills: [["path", { d: "M13 2 4 14h7l-1 8 9-12h-7z" }]],
  settings: [["circle", { cx: 12, cy: 12, r: 3 }], ["path", { d: "M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2.1 2.1M16.9 16.9 19 19M19 5l-2.1 2.1M7.1 16.9 5 19" }]],
  memory: [["path", { d: "M12 3a6 6 0 0 0-6 6c0 2 1 3 2 4v3h8v-3c1-1 2-2 2-4a6 6 0 0 0-6-6z" }], ["path", { d: "M9 20h6" }]],
  projects: [["path", { d: "M5 21V4M5 4h11l-2 4 2 4H5" }]],
  news: [["path", { d: "M5 4h11a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2V4z" }], ["path", { d: "M18 9h2v9a2 2 0 0 1-2 2M8 8h7M8 12h7M8 16h4" }]],
  approval: [["path", { d: "M12 3 4 7v5c0 5 3.5 8.5 8 10 4.5-1.5 8-5 8-10V7z" }], ["path", { d: "m9 12 2 2 4-4" }]],
  activity: [["path", { d: "M3 12h4l3-7 4 14 3-7h4" }]],
  sun: [["circle", { cx: 12, cy: 12, r: 4 }], ["path", { d: "M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" }]],
  moon: [["path", { d: "M20 14.5A8.5 8.5 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5z" }]],
  search: [["circle", { cx: 11, cy: 11, r: 6 }], ["path", { d: "m20 20-4.2-4.2" }]],
  bell: [["path", { d: "M6 9a6 6 0 1 1 12 0c0 5 2 6 2 6H4s2-1 2-6" }], ["path", { d: "M10 19a2 2 0 0 0 4 0" }]],
  mic: [["rect", { x: 9, y: 3, width: 6, height: 11, rx: 3 }], ["path", { d: "M5 11a7 7 0 0 0 14 0M12 18v3" }]],
  calendar: [["rect", { x: 3, y: 5, width: 18, height: 16, rx: 2 }], ["path", { d: "M3 10h18M8 3v4M16 3v4" }]],
  layers: [["path", { d: "m12 3 9 4.5-9 4.5-9-4.5z" }], ["path", { d: "m3 12 9 4.5 9-4.5M3 16.5 12 21l9-4.5" }]],
  sparkle: [["path", { d: "M12 3l1.8 4.8L18.5 9.5l-4.7 1.7L12 16l-1.8-4.8L5.5 9.5l4.7-1.7z" }]],
  chev: [["path", { d: "m9 6 6 6-6 6" }]],
  arrow: [["path", { d: "M5 12h14M13 6l6 6-6 6" }]],
  ext: [["path", { d: "M7 17 17 7M9 7h8v8" }]],
  gh: [["path", { d: "M9 19c-5 1.5-5-2.5-7-3m14 6v-3.9a3.4 3.4 0 0 0-1-2.6c3.1-.4 6.4-1.5 6.4-7a5.5 5.5 0 0 0-1.5-3.8 5.1 5.1 0 0 0-.1-3.8s-1.2-.4-3.9 1.5a13.4 13.4 0 0 0-7 0C6.2 1.9 5 2.3 5 2.3a5.1 5.1 0 0 0-.1 3.8A5.5 5.5 0 0 0 3.4 10c0 5.4 3.3 6.6 6.4 7a3.4 3.4 0 0 0-1 2.6V22" }]],
  plus: [["path", { d: "M12 5v14M5 12h14" }]],
  sliders: [["path", { d: "M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1" }], ["circle", { cx: 15, cy: 6, r: 2 }], ["circle", { cx: 9, cy: 12, r: 2 }], ["circle", { cx: 17, cy: 18, r: 2 }]],
  dots: [["circle", { cx: 5, cy: 12, r: 1.6 }], ["circle", { cx: 12, cy: 12, r: 1.6 }], ["circle", { cx: 19, cy: 12, r: 1.6 }]]
};
function ico(name, cls = "ico") {
  const parts = ICONS[name] || ICONS.skills;
  return sv("svg", { class: cls, viewBox: "0 0 24 24", "aria-hidden": "true" }, parts.map(([tag, attrs]) => sv(tag, attrs)));
}

function toast(msg) { const e = h("div", { class: "toast", text: msg }); document.body.append(e); setTimeout(() => e.remove(), 3200); }
async function api(path, opt = {}) {
  const o = { credentials: "same-origin", headers: { "Content-Type": "application/json" }, ...opt };
  if (o.body && typeof o.body !== "string" && !(o.body instanceof ArrayBuffer) && !(o.body instanceof Blob)) o.body = JSON.stringify(o.body);
  const r = await fetch("/api" + path, o);
  if (r.status === 401) { showLogin(); throw new Error("login"); }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r;
}
const post = (p, b) => api(p, { method: "POST", body: b || {} });
const del = p => api(p, { method: "DELETE" });
function when(ts) { return new Date(ts * 1000).toLocaleString(lang === "th" ? "th-TH" : undefined, { dateStyle: "short", timeStyle: "short" }); }
const view = () => $("#view");
const clear = () => { viewSerial++; view().replaceChildren(); return view(); };
function panel(title, ...kids) { return h("div", { class: "panel" }, title ? h("h3", null, h("span", { text: title })) : null, ...kids); }
function chips(items, cur, on) { return h("div", { class: "chips" }, items.map(([k, label]) => h("button", { class: "chip" + (k === cur ? " on" : ""), onclick: () => on(k), text: label }))); }
function field(label, el) { return h("div", null, h("label", { text: label }), el); }
const act = async (p, body, msg) => { const r = await post(p, body); if (r.ok === false) toast(r.error || r.message || "error"); else if (msg) toast(t(msg)); return r; };

// ---------- login ----------
function showLogin() {
  const v = clear(); $("#tabs").replaceChildren();
  const inp = h("input", { type: "password", placeholder: t("login_token"), autocomplete: "off" });
  const go = async () => { const r = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token: inp.value }) });
    if (r.ok) boot(); else toast(t("login_wrong")); };
  inp.addEventListener("keydown", e => e.key === "Enter" && go());
  v.append(panel(t("login_title"), h("p", { class: "dim", text: t("login_help") }), inp, h("p", null, h("button", { class: "pri", onclick: go, text: t("login_button") }))));
}
async function liffLogin() {
  if (!S._liff || !/Line\//i.test(navigator.userAgent)) return false;
  try {
    await new Promise((ok, no) => { const s = h("script", { src: "https://static.line-scdn.net/liff/edge/2/sdk.js" }); s.onload = ok; s.onerror = no; document.head.append(s); });
    await window.liff.init({ liffId: S._liff });
    if (!window.liff.isLoggedIn()) { window.liff.login(); return true; }
    const r = await fetch("/api/login/liff", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ idToken: window.liff.getIDToken() }) });
    return r.ok;
  } catch (e) { return false; }
}

// ---------- shell & theme ----------
const HUBS = [
  ["home", "home", "tab_home"],
  ["chat", "chat", "tab_chats"],
  ["manage", "layers", "tab_manage"],
  ["automation", "skills", "sub_auto"],
  ["customization", "sliders", "tab_custom"],
  ["computer", "system", "sub_system"],
  ["settings", "settings", "tab_settings"]
];
const MOBILE_HUBS = ["home", "chat", "manage", "automation"];
const MORE_HUBS = [["customization", "sliders", "tab_custom"], ["computer", "system", "sub_system"], ["settings", "settings", "tab_settings"]];
const TABS = ["home", "chat", "manage", "projects", "automation", "customization", "memory", "skills", "learning", "know", "mind", "computer", "activity", "work", "settings"];
const HUB_OF = { activity: "home", learning: "settings", know: "settings", mind: "settings", work: "computer", projects: "manage", memory: "customization", skills: "customization" };
let moreOpen = false;
function drawTabs() {
  const mobile = innerWidth <= 820;
  const hubBtn = ([k, ic, lb]) => h("button", { class: ((HUB_OF[tab] || tab) === k ? "on " : "") + (k === "computer" ? "nav-secondary" : ""), "data-tab": k, onclick: () => { moreOpen = false; go(k); } },
    h("span", { class: "nav-ico" }, ico(ic)),
    h("span", { class: "nav-lbl", text: k === "automation" && mobile ? (lang === "th" ? "ออโต้" : "Auto") : t(lb) }));
  const moreOn = mobile && ["customization", "computer", "settings"].includes(HUB_OF[tab] || tab);
  $("#tabs").replaceChildren(
    h("a", { class: "nav-brand brand-lockup", href: "/console", "aria-label": "nano Agent home" },
      h("span", { class: "logo-wrap" },
        h("img", { class: "logo logo-light-img", src: "/static/logo-light-theme.png", alt: "nano Agent" }),
        h("img", { class: "logo logo-dark-img", src: "/static/logo-dark-theme.png", alt: "" }))),
    ...HUBS.filter(([k]) => !mobile || MOBILE_HUBS.includes(k)).map(hubBtn),
    ...(mobile ? [h("button", { class: "more-btn" + (moreOn ? " on" : ""), "data-tab": "more", "aria-expanded": moreOpen ? "true" : "false",
      onclick: () => { moreOpen = !moreOpen; drawMore(); } },
      h("span", { class: "nav-ico" }, ico("dots")), h("span", { class: "nav-lbl", text: t("tab_more") }))] : []),
    h("a", { class: "oss-link", href: "https://github.com/julachok20/nano-agent", target: "_blank", rel: "noopener noreferrer" },
      h("span", { class: "oss-label" }, ico("gh"), h("span", { text: "Open Source" })), ico("ext")));
  drawMore();
}
// Mobile "More" sheet: Customization, System, Settings (same routes as the rail).
function drawMore() {
  let sheet = $("#more-sheet");
  if (!moreOpen || innerWidth > 820) { if (sheet) sheet.remove(); return; }
  if (!sheet) { sheet = h("div", { id: "more-sheet", class: "more-sheet" }); document.body.append(sheet); }
  sheet.replaceChildren(...MORE_HUBS.map(([k, ic, lb]) => h("button", { class: "more-item" + ((HUB_OF[tab] || tab) === k ? " on" : ""), "data-tab": k,
    onclick: () => { moreOpen = false; go(k); } }, ico(ic), h("span", { text: t(lb) }))), h("a", { class: "more-item", href: "https://github.com/julachok20/nano-agent", target: "_blank", rel: "noopener noreferrer" }, ico("gh"), h("span", { text: "Open Source" })));
}
function go(k) { tab = k; drawTabs(); render(); }
function render() { ({ home: vHome, chat: vChat, manage: vManage, projects: () => { sub.manage = "projects"; return vManage(); }, automation: vWork,
  customization: vCustom, memory: vCustom, skills: vCustom, computer: vSystem, settings: vSettings,
  activity: vWork, work: vWork, mind: vMind, learning: vMind, know: vMind })[tab](); setMascot(mascotState); }

function currentBaseTheme() {
  const th = document.documentElement.dataset.theme || "dark";
  return (th === "light" || th === "minimal") ? "light" : "dark";
}
function syncThemeButton() {
  const btn = $("#theme-quick");
  if (!btn) return;
  const isLight = currentBaseTheme() === "light";
  btn.replaceChildren(ico(isLight ? "moon" : "sun"));
  btn.title = isLight ? (lang === "th" ? "สลับเป็นโหมดมืด" : "Switch to Dark appearance") : (lang === "th" ? "สลับเป็นโหมดสว่าง" : "Switch to Light appearance");
}
function applyUi(p) {
  const r = document.documentElement;
  if (p["ui.accent"]) { r.dataset.accent = p["ui.accent"]; try { localStorage.setItem("nano.accent", p["ui.accent"]); } catch (e) {} }
  if (p["ui.theme"]) {
    const mapped = ({ spark: "dark", black: "modern" })[p["ui.theme"]] || p["ui.theme"];
    r.dataset.theme = mapped;
    try { localStorage.setItem("nano.theme", mapped); } catch (e) {}
  }
  if (p["ui.density"]) r.dataset.density = p["ui.density"];
  if (p["ui.text_size"]) r.dataset.size = p["ui.text_size"];
  syncThemeButton();
}
async function setTheme(next) {
  applyUi({ "ui.theme": next });
  if (tab === "settings") vSettings();
  if (tab === "customization") vCustom();
  try {
    const r = await post("/learning/pref", { setting: "ui.theme", value: next });
    if (r.ok && ME.prefs) ME.prefs["ui.theme"] = next;
  } catch (e) { /* localStorage still keeps the choice */ }
}
function wireHeaderActions() {
  const tBtn = $("#theme-quick");
  if (tBtn && !tBtn.dataset.wired) {
    tBtn.dataset.wired = "1";
    tBtn.addEventListener("click", () => setTheme(currentBaseTheme() === "light" ? "dark" : "light"));
    syncThemeButton();
  }
  const sBtn = $("#hdr-search");
  if (sBtn && !sBtn.dataset.wired) {
    sBtn.dataset.wired = "1";
    sBtn.replaceChildren(ico("search"));
    sBtn.title = t("tab_chat");
    sBtn.addEventListener("click", () => go("chat"));
  }
  const nBtn = $("#hdr-notif");
  if (nBtn && !nBtn.dataset.wired) {
    nBtn.dataset.wired = "1";
    nBtn.replaceChildren(ico("bell"));
    nBtn.title = t("sub_drafts");
    nBtn.addEventListener("click", () => { sub.manage = "drafts"; go("manage"); });
  }
}
function viewHeading(title, detail, number) {
  return h("div", { class: "view-heading" }, h("div", null, h("small", { text: `NANO AGENT / ${String(number).padStart(2, "0")}` }), h("h1", { text: title }), h("p", { text: detail })));
}
async function pollPill() {
  try { const r = await api("/activity?count=1"); const n = r.running || 0; const p = $("#pill"); p.classList.toggle("busy", n > 0);
    $("#pilltxt").textContent = n > 0 ? t("pill_busy", { n }) : t("pill_idle");
    const orb = $("#orb"); if (orb) orb.dataset.working = n > 0 ? "true" : "false";
  } catch (e) { /* login screen */ }
}

// ---------- home ----------
let openerSpoken = false, orbState = "idle", rec = null;
const setOrb = s => { orbState = s; const o = $("#orb"); if (o) o.dataset.state = s; setMascot(s === "idle" ? mascotIdleState() : s); };
function speak(text) {
  return new Promise(async res => {
    setOrb("speaking");
    try {
      if (ME.voice && ME.voice.server_tts) { const r = await api("/voice/tts", { method: "POST", body: { text } }); if (r.ok) { const a = new Audio(URL.createObjectURL(await r.blob())); a.onended = res; await a.play(); return; } }
      if ("speechSynthesis" in window) { const u = new SpeechSynthesisUtterance(text); u.lang = lang === "th" ? "th-TH" : "en-US"; u.onend = res; speechSynthesis.speak(u); return; }
    } catch (e) { /* fall through */ }
    res();
  }).finally(() => setOrb("idle"));
}
async function ask(text, session, role = "chat") {
  return post("/chat", { text, session, role });
}
function listen() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { toast(t("voice_unsupported")); return; }
  rec = new SR(); rec.lang = lang === "th" ? "th-TH" : "en-US"; rec.interimResults = false;
  setOrb("listening");
  rec.onresult = async e => { const said = e.results[0][0].transcript; setOrb("thinking"); $("#heard").textContent = said;
    try { const r = await ask(said, "voice", chatRole); $("#said").textContent = r.text || ""; await speak(r.text || ""); refreshHome(); } catch (x) { setOrb("idle"); } };
  rec.onerror = () => setOrb("idle"); rec.onend = () => { if (orbState === "listening") setOrb("idle"); };
  rec.start();
}
async function orbTap() {
  if (orbState === "listening" && rec) { rec.stop(); return; }
  if (orbState !== "idle") return;
  if (!openerSpoken) { openerSpoken = true; const o = await api("/companion/opener"); $("#said").textContent = o.text; await speak(o.text); return; }
  listen();
}
function jvPanel(area, iconName, title, target, section, ...kids) {
  const head = h("div", { class: "jv-panel-head" },
    h("span", { class: "jv-h-left" }, ico(iconName), h("span", { text: title })),
    target ? h("button", { class: "jv-chev", "aria-label": title, onclick: () => { if (section) sub[target] = section; go(target); } }, ico("chev")) : null);
  return h("section", { class: "jv-panel", style: area ? `grid-area:${area}` : "" }, head, ...kids);
}
function jvEmpty(iconName, message) {
  return h("div", { class: "jv-empty-box" }, ico(iconName), h("p", { class: "jv-note", text: message }));
}
function jvMemoryGraph(count) {
  const svg = sv("svg", { class: "jv-memory-graph", viewBox: "0 0 300 100", "aria-hidden": "true" });
  const points = [[54, 24], [108, 16], [156, 22], [228, 30], [250, 74], [198, 86], [112, 86], [48, 70]];
  points.slice(0, Math.min(count, points.length)).forEach(([x, y], i) => {
    svg.append(sv("line", { x1: 150, y1: 52, x2: x, y2: y, stroke: "var(--accent-2)", "stroke-opacity": 0.45, "stroke-width": 1.6 }),
      sv("circle", { cx: x, cy: y, r: 5, fill: ["var(--accent-2)", "var(--accent)", "var(--warn)", "var(--ok)"][i % 4] }));
  });
  const center = sv("text", { x: 150, y: 57, "text-anchor": "middle", fill: "var(--txt)", "font-size": 13, "font-weight": 700 }); center.textContent = String(count);
  svg.append(sv("circle", { cx: 150, cy: 52, r: 16, fill: "var(--bg-elev)", stroke: "var(--accent-2)", "stroke-width": 2 }), center);
  return svg;
}
function startChatWith(promptText) {
  sub.chatDraft = promptText;
  go("chat");
}
function waveBars(n = 5) {
  return h("div", { class: "orb-wave", "aria-hidden": "true" },
    ...Array.from({ length: n }, (_, i) => h("i", { style: `--i:${i};--h:${[14, 24, 34, 22, 12][i % 5]}px` })));
}
// Mascot "n" (DESIGN-SPEC 3.8): the one swappable slot. Swap this SVG to change the mascot; CSS handles blink, gaze and states.
function mascotSlot() {
  return h("div", { class: "mascot", "data-mascot": "main" });
}
// Sub-agent letter slots (DESIGN-SPEC 3.9). Visual only: no sub-agent data exists yet, so nothing is shown as running.
function agentSlots() {
  return h("div", { class: "agent-block" },
    h("div", { class: "agent-slots", "aria-hidden": "true" }, ...[0, 1, 2].map(() => h("span", { class: "agent-letter", text: "·" }))),
    h("p", { class: "agent-caption", text: lang === "th" ? "ซับเอเจนต์จะแสดงที่นี่เมื่อทำงาน" : "Sub-agents appear here when running" }));
}
async function vHome() {
  const v = clear();
  const date = new Date(), hour = date.getHours();
  const greeting = lang === "th" ? (hour < 11 ? "สวัสดีตอนเช้า" : hour < 17 ? "สวัสดีตอนบ่าย" : "สวัสดีตอนเย็น")
    : (hour < 11 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening");
  // Mic state comes from the browser: "Listening ready" only when speech recognition exists.
  const voiceOk = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  const askInp = h("input", { placeholder: lang === "th" ? "ถามอะไรก็ได้..." : "Ask anything, or type a command...", "aria-label": t("chat_placeholder") });
  const submitQuick = () => {
    const q = askInp.value.trim();
    if (q) startChatWith(q);
    else go("chat");
  };
  const sendBtn = h("button", { class: "pri", onclick: submitQuick, "aria-label": t("send"), disabled: true }, ico("arrow"));
  askInp.addEventListener("input", () => { sendBtn.disabled = !askInp.value.trim(); });
  askInp.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); submitQuick(); } });

  const subline = lang === "th"
    ? h("p", { class: "jv-subline" }, "ผู้ช่วย AI ส่วนตัวแบบโอเพ่นซอร์ส พร้อม ", h("b", { text: "พูด ฟัง และลงมือทำ" }), " เพื่อคุณ")
    : h("p", { class: "jv-subline" }, "Your open-source personal AI assistant. I can ", h("b", { text: "speak, listen, think, and take action" }), " for you.");

  v.append(
    h("div", { class: "jv-head" },
      h("div", null,
        h("small", { text: date.toLocaleDateString(lang === "th" ? "th-TH" : undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" }) }),
        h("strong", { text: greeting + (ME.owner_name ? ", " + ME.owner_name : "") }),
        subline),
      h("div", { id: "home-clock", class: "jv-clock" })),
    h("div", { class: "jv-grid" },
      h("div", { id: "home-task-panel", class: "jv-slot", style: "grid-area:task" }),
      h("div", { id: "home-memory-panel", class: "jv-slot", style: "grid-area:mem" }),
      h("section", { class: "jv-center", style: "grid-area:center" },
        h("div", { class: "orb-stage" },
          h("div", { class: "orb-chips" },
            h("button", { class: "orb-chip orb-chip-top", onclick: orbTap }, ico("mic"), h("span", { text: lang === "th" ? "คุย" : "Talk" })),
            h("button", { class: "orb-chip orb-chip-lt", onclick: () => go("chat") }, ico("chat"), h("span", { text: lang === "th" ? "ถาม" : "Ask" })),
            h("button", { class: "orb-chip orb-chip-rt", onclick: () => startChatWith(lang === "th" ? "ช่วยวางแผนวันนี้" : "Plan my day") }, ico("calendar"), h("span", { text: lang === "th" ? "วางแผน" : "Plan" })),
            h("button", { class: "orb-chip orb-chip-lb", onclick: () => go("memory") }, ico("layers"), h("span", { text: lang === "th" ? "ความจำ" : "Remember" })),
            h("button", { class: "orb-chip orb-chip-rb", onclick: () => go("automation") }, ico("skills"), h("span", { text: lang === "th" ? "อัตโนมัติ" : "Automate" }))),
          h("div", { class: "orb-aura" },
            h("button", { id: "orb", class: "jv-orb" + (voiceOk ? "" : " unavailable"), "data-state": "idle", onclick: orbTap, "aria-label": t("orb_tap") },
              mascotSlot(),
              h("strong", { text: lang === "th" ? "แตะเพื่อพูด" : "Tap to speak" }),
              h("small", null, h("i"), h("span", { text: voiceOk ? (lang === "th" ? "พร้อมรับฟัง" : "Listening ready") : (lang === "th" ? "ไม่มีระบบเสียง" : "Voice unavailable") }))))),
        h("div", { class: "mic-row" },
          waveBars(5),
          h("button", { class: "home-mic", onclick: orbTap, "aria-label": voiceOk ? t("orb_tap") : t("voice_unsupported"),
            title: voiceOk ? "" : t("voice_unsupported"), ...(voiceOk ? {} : { disabled: true }) }, ico("mic")),
          waveBars(5)),
        h("div", { id: "heard", class: "jv-heard" }),
        h("div", { id: "said", class: "jv-said" }),
        h("div", { class: "quick-ask" },
          h("button", { class: "plus-btn", type: "button", disabled: true, "aria-label": lang === "th" ? "แนบไฟล์ (ยังไม่พร้อมใช้งาน)" : "Attach (not available yet)" }, ico("plus")),
          askInp,
          sendBtn)),
      h("div", { id: "home-system-panel", class: "jv-slot", style: "grid-area:appr" }),
      h("div", { id: "home-activity-panel", class: "jv-slot", style: "grid-area:bg" }),
      h("div", { class: "jv-bottom intelligence-flow" },
        h("div", { class: "flow-intro" }, h("small", { text: "INTELLIGENCE FLOW" }),
          h("strong", { text: "From understanding to action." }),
          h("p", { text: "A system that understands, reasons, and gets things done for you." })),
        h("div", { class: "flow-steps" },
          ...[["Input", "Text · Voice · File", "news"], ["Understand", "Perception", "memory"],
            ["Reason", "Plan · Decide", "layers"], ["Act", "Tools · Automations", "skills"],
            ["Learn", "Memory · Adapt", "projects"]].flatMap(([name, detail, icon], i) => {
            const step = h("div", { class: "flow-step" }, ico(icon), h("b", { text: name }), h("small", { text: detail }));
            return i ? [h("span", { class: "flow-arrow" }, ico("arrow")), step] : [step];
          })))));
  refreshHome();
}
async function refreshHome() {
  if (tab !== "home") return;
  const [st, tk, ac] = await Promise.all([api("/state"), api("/tasks"), api("/activity")]);
  if (!$("#home-task-panel")) return;
  const factCount = (st.memory.fact || 0) + (st.memory.rule || 0);
  $("#home-clock").textContent = new Date().toLocaleTimeString(lang === "th" ? "th-TH" : undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
  const openTasks = tk.tasks.filter(x => !x.done);
  const totalTasks = tk.tasks.length;
  const completed = totalTasks - openTasks.length, pct = totalTasks ? completed / totalTasks : 0;
  $("#home-task-panel").replaceChildren(jvPanel("task", "manage", t("sub_tasks"), "manage", null,
    h("div", { class: "jv-ringrow" },
      h("div", { class: "jv-ring", style: `--done:${Math.round(pct * 100)}%` }, h("span", { text: `${completed}/${totalTasks}` })),
      h("div", { class: "jv-task-rows" }, openTasks.length
        ? openTasks.slice(0, 3).map(x => h("div", { class: "jv-row" }, h("span", { class: "jv-dot" }), h("span", { class: "jv-name", text: x.title })))
        : jvEmpty("manage", totalTasks ? (lang === "th" ? "ไม่มีงานค้าง" : "All caught up") : (lang === "th" ? "ยังไม่มีงาน" : "No tasks yet"))))));
  $("#home-memory-panel").replaceChildren(jvPanel("mem", "memory", t("memory_title"), "memory", null,
    factCount ? jvMemoryGraph(factCount) : jvEmpty("memory", lang === "th" ? "ยังไม่มีความจำ" : "No memories yet"),
    h("div", { class: "jv-pct" }, h("strong", { text: `${factCount} memories` }), h("small", { text: t("memory_counts", { f: st.memory.fact || 0, r: st.memory.rule || 0 }) }))));
  $("#home-system-panel").replaceChildren(jvPanel("appr", "activity", lang === "th" ? "สถานะระบบ" : "System Status", "computer", null,
    h("span", { class: "system-active", text: lang === "th" ? "● พร้อมใช้งาน" : "● Active" }),
    ...[["Model", ME.model || "Configured model", "computer"], ["Memory", `${factCount} items`, "memory"], ["Skills", "View skills", "skills"]]
      .map(([name, value, icon]) => h("div", { class: "system-status-row" }, ico(icon), h("b", { text: name }), h("span", { text: value }), ico("chev")))));
  const recent = [...ac.running, ...ac.done.slice(0, 3)];
  $("#home-activity-panel").replaceChildren(jvPanel("bg", "activity", t("work_title"), "activity", null,
    recent.length ? recent.map(a => h("div", { class: "jv-activity-row" }, h("span", { class: "jv-dot " + (a.status === "running" ? "running" : "") }),
      h("span", { text: a.title }), h("small", { text: a.status === "running" ? Math.round(a.secs) + "s" : a.status }))) : jvEmpty("activity", lang === "th" ? t("work_idle") : "No background work right now."), agentSlots()));
  // Bell dot = real pending approvals (drafts waiting for the owner), nothing else.
  const bell = $("#hdr-notif");
  pendingApprovals = (st.drafts || 0) + (st.capabilities || 0); updateBellDot();
}
function draftsPanel(list, after) {
  return panel(t("drafts_title", { n: list.length }), h("p", { class: "dim", text: t("drafts_note") }), ...list.map(d => h("div", { class: "row" },
    h("span", { class: "tag", text: d.channel + " → " + d.target }), h("div", { class: "grow", text: d.text }),
    h("button", { class: "pri", onclick: async () => { const r = await post("/drafts/" + d.id + "/approve"); toast(r.ok ? t("drafts_sent") : r.error); after(); }, text: t("approve_send") }),
    h("button", { class: "bad", onclick: async () => { await post("/drafts/" + d.id + "/cancel"); after(); }, text: t("cancel") }))));
}

// ---------- chat ----------
function modelChoices() {
  const m = ME.models || {};
  const entries = [
    ["chat", m.chat || ME.model || "default", lang === "th" ? "หลัก" : "Chat"],
    ["fast", m.fast, lang === "th" ? "เร็ว" : "Fast"],
    ["vision", m.vision, lang === "th" ? "ภาพ" : "Vision"]
  ].filter(([, name]) => Boolean(name));
  return entries.length ? entries : [["chat", ME.model || "AI assistant", "Chat"]];
}
// ---------- mascot: one automatic state (idle, listening, thinking, speaking, happy, sleeping) ----------
let MASCOT_TPL = null, mascotState = "idle", lastActive = Date.now();
function parseSvgText(str) { return new DOMParser().parseFromString(str, "image/svg+xml").documentElement; }
async function loadMascots() {
  if (!MASCOT_TPL) MASCOT_TPL = parseSvgText(await (await fetch("/static/mascot-n.svg")).text());
}
// App states that have no art of their own reuse a sample's look: done = happy, error = error (styled in dashboard.css).
const SVG_STATE = { working: "working", waiting: "waiting", done: "happy", error: "error" };
let bgRunning = false, pendingApprovals = 0;
function mascotIdleState() { return pendingApprovals ? "waiting" : bgRunning ? "working" : "idle"; }
function mascotNode(state) {
  const el = document.importNode(MASCOT_TPL, true);
  el.setAttribute("class", "mascot-n is-" + (SVG_STATE[state] || state));
  el.setAttribute("role", "img"); el.setAttribute("aria-label", "nano Agent, " + state);
  return el;
}
// Sub-agent slot: derived look from subagents.js; empty slot shows a dashed outline and never animates.
function subSlotNode() {
  return window.Subagents ? document.importNode(parseSvgText(window.Subagents.svg("", "idle")), true) : h("span", { text: "·" });
}
function setMascot(s) {
  mascotState = s;
  if (!MASCOT_TPL) return;
  document.querySelectorAll("[data-mascot]").forEach(el => el.replaceChildren(mascotNode(s)));
}
// Bell dot = waiting approvals, shown on every page (updated by the poll), unless the owner switched notices off on this device.
function updateBellDot() {
  const bell = $("#hdr-notif");
  if (!bell) return;
  const old = bell.querySelector(".notif-dot"); if (old) old.remove();
  if (pendingApprovals > 0 && approvalNoticesOn()) bell.append(h("span", { class: "notif-dot" }));
}
// Background work and pending approvals drive the idle-side states; the poll never touches thinking, listening, speaking, done or error.
async function mascotPoll() {
  try {
    const st = await api("/state");
    bgRunning = (st.running || 0) > 0; pendingApprovals = (st.drafts || 0) + (st.capabilities || 0); updateBellDot();
    if (["idle", "working", "waiting", "sleeping"].includes(mascotState)) {
      const next = mascotIdleState();
      setMascot(next === "idle" && mascotState === "sleeping" ? "sleeping" : next);
    }
  } catch (e) { /* login screen or offline: keep the current state */ }
}
function startMascotClock() {
  setInterval(mascotPoll, 5000);
  ["pointerdown", "keydown"].forEach(ev => addEventListener(ev, () => { lastActive = Date.now(); if (mascotState === "sleeping") setMascot("idle"); }));
  setInterval(() => { if (mascotState === "idle" && Date.now() - lastActive > 10 * 60 * 1000) setMascot("sleeping"); }, 60 * 1000);
}

// ---------- chats: three panes (agents + conversations | thread | context). Real data only. ----------
// On this device only: whether the bell shows a dot for waiting approvals. Sends nothing anywhere.
function approvalNoticesOn() { try { return localStorage.getItem("nano.notify.approvals") !== "off"; } catch (e) { return true; } }
// Capability card (addendum section 3): what the AI wants, why, and Allow / Deny. Both need the one-time code on this card.
// The reason is plain text from the model. Allowing records a grant only; no connector call happens in v0.2.
function capabilityCard(c) {
  const codeIn = h("input", { class: "cap-code", type: "text", maxlength: 12, autocomplete: "off",
    placeholder: lang === "th" ? "รหัสครั้งเดียว" : "One-time code", "aria-label": lang === "th" ? "รหัสครั้งเดียว" : "One-time code" });
  const decide = kind => async () => {
    const r = await post("/capabilities/" + c.id + "/" + kind, { code: codeIn.value });
    toast(r.ok ? (kind === "allow" ? (lang === "th" ? "อนุญาตแล้ว" : "Allowed") : (lang === "th" ? "ปฏิเสธแล้ว" : "Denied")) : r.error);
    vChat();
  };
  return h("div", { class: "approval-card capability-card" },
    h("b", { text: lang === "th" ? "คำขอสิทธิ์ (ยังไม่อนุญาต)" : "Capability request (not allowed yet)" }),
    h("span", { class: "tag", text: c.connector + " · " + c.scope }),
    h("p", { class: "approval-text", text: (lang === "th" ? "ต้องการ: " : "Wants: ") + String(c.actions).split(",").join(", ") }),
    h("p", { class: "approval-text", text: (lang === "th" ? "เหตุผล: " : "Why: ") + c.reason }),
    h("p", { class: "dim", text: (lang === "th" ? "รหัสของคำขอนี้: " : "Code for this request: ") + c.code }),
    h("div", { class: "approval-actions" }, codeIn,
      h("button", { class: "pri", onclick: decide("allow"), text: lang === "th" ? "อนุญาต" : "Allow" }),
      h("button", { class: "bad", onclick: decide("deny"), text: lang === "th" ? "ปฏิเสธ" : "Deny" })));
}
// Approval card: approve and cancel use the existing /drafts routes. Edit changes the pending text only; approval is still needed.
function approvalCard(d) {
  const body = h("p", { class: "approval-text", text: d.text });
  const editBox = h("textarea", { class: "approval-edit", rows: 3, "aria-label": lang === "th" ? "แก้ข้อความที่รออนุมัติ" : "Edit the waiting message", hidden: true });
  editBox.value = d.text;
  const saveBtn = h("button", { class: "pri", hidden: true, text: lang === "th" ? "บันทึก" : "Save", onclick: async () => {
    const r = await post("/drafts/" + d.id + "/edit", { text: editBox.value }); toast(r.ok ? t("saved") : r.error); vChat(); } });
  const editBtn = h("button", { onclick: () => { const on = editBox.hidden; editBox.hidden = !on; saveBtn.hidden = !on; body.hidden = on; editBtn.textContent = on ? (lang === "th" ? "ยกเลิก" : "Cancel edit") : (lang === "th" ? "แก้ไข" : "Edit"); },
    text: lang === "th" ? "แก้ไข" : "Edit" });
  return h("div", { class: "approval-card" },
    h("b", { text: lang === "th" ? "รออนุมัติ" : "Approval needed" }),
    h("span", { class: "tag", text: d.channel + " → " + d.target }),
    body, editBox,
    h("div", { class: "approval-actions" },
      h("button", { class: "pri", onclick: async () => { const r = await post("/drafts/" + d.id + "/approve"); toast(r.ok ? t("drafts_sent") : r.error); vChat(); }, text: t("approve_send") }),
      editBtn, saveBtn,
      h("button", { class: "bad", onclick: async () => { await post("/drafts/" + d.id + "/cancel"); vChat(); }, text: t("cancel") })));
}
function messageBlocks(role, text) {
  const wrap = h("div", { class: "msg-wrap " + role });
  String(text || "").split("```").forEach((part, i) => {
    if (i % 2) {
      const nl = part.indexOf("\n"), code = (nl >= 0 ? part.slice(nl + 1) : part).replace(/\n$/, ""), label = nl >= 0 ? part.slice(0, nl).trim() : "";
      // ```ui fence = generative UI blocks (uiblocks.js). Model answers are untrusted: chart and stat are dropped. Invalid JSON falls back to a code block.
      if (label === "ui" && window.UIBlocks) {
        const ans = UIBlocks.parse(code, { trusted: false });
        if (ans) { wrap.append(UIBlocks.render(ans, { note: lang === "th" ? "บางบล็อกไม่แสดง (ไม่รองรับหรือข้อมูลไม่ถูกต้อง)" : "Some blocks were not shown (unsupported or invalid)." })); return; }
      }
      wrap.append(h("div", { class: "code-block" },
        h("div", { class: "code-head" }, h("small", { text: label || "code" }),
          h("button", { type: "button", onclick: () => { if (navigator.clipboard) navigator.clipboard.writeText(code); }, text: lang === "th" ? "คัดลอก" : "Copy" })),
        h("pre", { text: code })));
    } else if (part.trim()) wrap.append(h("div", { class: "msg " + role, text: part.trim() }));
  });
  return wrap;
}
async function vChat() {
  const v = clear(), serial = viewSerial;
  const [hist, st, dr, capRes] = await Promise.all([api("/history?session=console"), api("/state"), api("/drafts"), api("/capabilities")]);
  if (serial !== viewSerial) return;
  const msgs = hist.messages || [], drafts = dr.drafts || [], caps = capRes.pending || [];
  const choices = modelChoices();
  if (!choices.some(([r]) => r === chatRole)) chatRole = choices[0][0];
  const activeModel = () => (choices.find(([r]) => r === chatRole) || choices[0])[1];
  const showCtx = sub.chatContext !== false, onThread = sub.chatView === "thread";
  const filter = (sub.chatFilter || "").trim().toLowerCase();
  const first = msgs.find(m => m.role === "user"), last = msgs.length ? msgs[msgs.length - 1] : null;
  const convTitle = first ? first.text.slice(0, 48) : (lang === "th" ? "การสนทนากับหลัก" : "Conversation with Main");
  const matches = !filter || convTitle.toLowerCase().includes(filter) || (last && last.text.toLowerCase().includes(filter));
  const openThread = () => { sub.chatView = "thread"; vChat(); };
  const kind = sub.chatKind || "all";
  const showConv = kind !== "pinned" && msgs.length > 0 && matches;

  const inp = h("textarea", { placeholder: t("chat_placeholder"), rows: 2, "aria-label": t("chat_placeholder") });
  if (sub.chatDraft) { inp.value = sub.chatDraft; delete sub.chatDraft; }
  const box = h("div", { id: "chatbox", class: "chat-messages", role: "log", "aria-live": "polite" });
  if (!msgs.length) {
    const starters = lang === "th" ? ["ช่วยวางแผนงานวันนี้", "สรุปงานที่ค้างอยู่"] : ["Plan my day", "Summarize my open tasks"];
    box.append(h("div", { class: "chat-empty" }, h("span", { class: "chat-av-big", "data-mascot": "main" }),
      h("h2", { text: lang === "th" ? "เริ่มการสนทนากับหลัก" : "Start a conversation with Main" }),
      h("div", { class: "jv-quick-prompts" }, ...starters.map(s => h("button", { onclick: () => { inp.value = s; inp.focus(); }, text: s })))));
  }
  msgs.forEach(m => box.append(messageBlocks(m.role, m.text)));
  drafts.forEach(d => box.append(approvalCard(d)));
  caps.forEach(c => box.append(capabilityCard(c)));

  const send = async () => {
    const text = inp.value.trim(); if (!text) return; inp.value = "";
    box.querySelector(".chat-empty")?.remove();
    box.append(h("div", { class: "msg user", text }));
    const wait = h("div", { class: "msg note", text: t("chat_thinking") }); box.append(wait);
    setMascot("thinking");
    try {
      const r = await ask(text, "console", chatRole); wait.remove();
      box.append(messageBlocks("assistant", r.text || ""));
      (r.tools || []).forEach(x => box.append(h("details", { class: "tool-card" }, h("summary", { text: (lang === "th" ? "ใช้เครื่องมือ: " : "Used tool: ") + x.name }))));
      (r.new_drafts || []).forEach(d => box.append(approvalCard(d)));
      setMascot("done"); setTimeout(() => { if (mascotState === "done") { setMascot("idle"); mascotPoll(); } }, 2500);
    } catch (e) { wait.remove(); setMascot("error"); setTimeout(() => { if (mascotState === "error") { setMascot("idle"); mascotPoll(); } }, 4000); }
    box.scrollTop = box.scrollHeight;
  };
  inp.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
  // "/" menu: typed at the start of the composer. Each command does a real app action or is marked not available.
  const SLASH = [["/new", lang === "th" ? "แชทใหม่ (ยังไม่พร้อม)" : "New chat (not available yet)", null],
    ["/model", lang === "th" ? "เปลี่ยนโมเดล" : "Change model", () => modelSelect.focus()],
    ["/memory", lang === "th" ? "เปิดความจำ" : "Open memory", () => go("customization")],
    ["/tasks", lang === "th" ? "เปิดงาน" : "Open tasks", () => go("manage")]];
  const slash = h("div", { class: "slash-menu", role: "listbox" });
  const renderSlash = () => {
    const q = inp.value.trim().toLowerCase();
    if (!inp.value.startsWith("/")) { slash.replaceChildren(); return; }
    const hits = SLASH.filter(([c]) => c.startsWith(q.split(" ")[0]));
    slash.replaceChildren(...hits.map(([c, label, fn]) => h("button", { class: "slash-item", type: "button", disabled: !fn, role: "option",
      onclick: () => { inp.value = ""; slash.replaceChildren(); if (fn) fn(); }, text: c + " · " + label })));
  };
  inp.addEventListener("input", renderSlash);

  const subRow = i => h("div", { class: "agent-row dim", "aria-disabled": "true" }, h("span", { class: "agent-av" }, subSlotNode()),
    h("span", { class: "grow", text: (lang === "th" ? "ช่องซับเอเจนต์ " : "Sub-agent slot ") + (i + 1) }), h("small", { text: lang === "th" ? "ยังไม่ได้ตั้งค่า" : "Not set up" }));
  const modelSelect = h("select", { class: "model-select", "aria-label": t("model_label"), onchange: e => { chatRole = e.target.value; } },
    choices.map(([role, name, label]) => h("option", { value: role, selected: role === chatRole ? "" : null, text: `${label}: ${name}` })));
  const crow = (k, val) => h("div", { class: "row" }, h("b", { text: k }), h("span", { class: "dim grow", text: val == null || val === "" ? (lang === "th" ? "ไม่มีข้อมูล" : "Not available") : String(val) }));
  const memTotal = Object.values(st.memory || {}).reduce((a, b) => a + (typeof b === "number" ? b : 0), 0);

  v.append(h("section", { class: "chats-layout" + (showCtx ? "" : " no-ctx") + (onThread ? " view-thread" : " view-list") },
    h("aside", { class: "chat-list-pane" },
      h("input", { class: "chat-search", type: "search", value: sub.chatFilter || "", placeholder: lang === "th" ? "ค้นหาแชท" : "Search chats",
        "aria-label": lang === "th" ? "ค้นหาแชท" : "Search chats", oninput: e => { sub.chatFilter = e.target.value; } }),
      h("button", { class: "new-chat", disabled: true, title: lang === "th" ? "ยังไม่พร้อมใช้งาน" : "Not available yet", text: lang === "th" ? "แชทใหม่ (ยังไม่พร้อม)" : "New chat (not available yet)" }),
      h("h5", { text: lang === "th" ? "เอเจนต์" : "Agents" }),
      h("button", { class: "agent-row on", onclick: openThread }, h("span", { class: "agent-av", "data-mascot": "main" }), h("span", { class: "grow", text: "Main" }), h("small", { text: lang === "th" ? "พร้อม" : "Ready" })),
      subRow(0), subRow(1), subRow(2),
      h("h5", { text: lang === "th" ? "การสนทนา" : "Conversations" }),
      chips([["all", lang === "th" ? "ทั้งหมด" : "All"], ["pinned", lang === "th" ? "ปักหมุด" : "Pinned"], ["main", "Main"]], kind, k => { sub.chatKind = k; vChat(); }),
      showConv
        ? h("button", { class: "conv-row on", onclick: openThread }, h("b", { text: convTitle }), h("small", { text: last ? last.text.slice(0, 70) : "" }))
        : h("p", { class: "dim", text: kind === "pinned" ? (lang === "th" ? "ยังไม่มีแชทที่ปักหมุด (การปักหมุดยังไม่พร้อมใช้งาน)" : "No pinned chats. Pinning is not available yet.")
          : msgs.length ? (lang === "th" ? "ไม่มีแชทที่ตรงกัน" : "No chats match") : (lang === "th" ? "ยังไม่มีแชท" : "No chats yet") })),
    h("section", { class: "chat-thread-pane" },
      h("div", { class: "agent-chips", role: "tablist", "aria-label": lang === "th" ? "เอเจนต์" : "Agents" },
        h("button", { class: "chip on", role: "tab", "aria-selected": "true", onclick: openThread, text: "Main" }),
        [1, 2, 3].map(i => h("button", { class: "chip", role: "tab", "aria-selected": "false", disabled: true, title: lang === "th" ? "ยังไม่ได้ตั้งค่า" : "Not set up", text: (lang === "th" ? "ช่อง " : "Slot ") + i }))),
      h("header", { class: "chat-head" },
        h("button", { class: "chat-back", "aria-label": lang === "th" ? "กลับ" : "Back", onclick: () => { sub.chatView = "list"; vChat(); } }, ico("chev")),
        h("span", { class: "chat-av", "data-mascot": "main" }),
        h("div", { class: "chat-head-info" }, h("strong", { text: "Main" }), h("small", { text: lang === "th" ? "พร้อม" : "Ready" })),
        h("div", { class: "chat-head-controls" }, modelSelect,
          h("button", { class: "ctx-toggle", "aria-pressed": showCtx ? "true" : "false", onclick: () => { sub.chatContext = !showCtx; vChat(); }, text: lang === "th" ? "รายละเอียด" : "Details" }))),
      box,
      h("div", { class: "chat-composer" }, slash, inp, h("div", { class: "chat-composer-bottom" },
        h("small", { text: lang === "th" ? "Enter เพื่อส่ง · Shift+Enter ขึ้นบรรทัดใหม่" : "Enter to send · Shift+Enter for a new line" }),
        h("span", { class: "composer-tools" },
          h("button", { type: "button", disabled: true, title: lang === "th" ? "ยังไม่พร้อมใช้งาน" : "Not available yet", "aria-label": lang === "th" ? "แนบไฟล์ (ยังไม่พร้อม)" : "Attach (not available yet)" }, ico("plus")),
          h("button", { class: "pri", onclick: send, text: t("send") + " →" }))))),
    showCtx ? h("aside", { class: "chat-context" },
      h("h4", { text: lang === "th" ? "บริบทของแชท" : "Chat context" }),
      crow(lang === "th" ? "เอเจนต์" : "Agent", "Main"),
      crow(lang === "th" ? "โมเดล" : "Model", activeModel()),
      crow(lang === "th" ? "ความจำที่มี" : "Memory items", memTotal),
      crow(lang === "th" ? "รออนุมัติ" : "Approvals waiting", drafts.length),
      crow(lang === "th" ? "งานค้าง" : "Open tasks", st.open_tasks),
      crow(lang === "th" ? "ไฟล์" : "Files", null),
      crow(lang === "th" ? "งานที่สร้างในแชทนี้" : "Tasks created here", null)) : null));
  box.scrollTop = box.scrollHeight;
  setMascot(mascotState);
}

// ---------- manage ----------
async function vProjects() { sub.manage = "projects"; await vManage(); }
async function renderProjects(v, serial) {
  const data = await api("/projects"), items = data.items || [];
  if (serial !== viewSerial) return;
  const name = h("input", { placeholder: lang === "th" ? "ชื่อโปรเจกต์" : "Project name", maxlength: 100 });
  const goal = h("input", { placeholder: lang === "th" ? "เป้าหมาย" : "Goal", maxlength: 500 });
  const deadline = h("input", { type: "date", "aria-label": lang === "th" ? "กำหนดส่ง" : "Deadline" });
  const next = h("input", { placeholder: lang === "th" ? "ขั้นต่อไป" : "Next step", maxlength: 300 });
  v.append(
    h("div", { class: "page-summary" },
      h("strong", { text: String(items.length) }), h("span", { text: lang === "th" ? "โปรเจกต์ที่กำลังทำ" : "active projects" })),
    panel(lang === "th" ? "เริ่มโปรเจกต์" : "Start a project",
      h("div", { class: "project-form" }, name, goal, deadline, next),
      h("button", { class: "pri", onclick: async () => { const r = await act("/projects", { name: name.value, goal: goal.value, deadline: deadline.value, next_step: next.value }); if (r.ok) vProjects(); }, text: lang === "th" ? "สร้างโปรเจกต์" : "Create project" })));
  if (!items.length) v.append(panel(lang === "th" ? "โปรเจกต์ของคุณ" : "Your projects",
    h("div", { class: "jv-empty-box" }, ico("projects", "ico ico-lg"),
      h("p", { class: "jv-note", text: lang === "th" ? "ยังไม่มีโปรเจกต์ เริ่มจากชื่อและเป้าหมายด้านบน" : "No projects yet. Add a name and goal above." }))));
  for (const p of items) {
    const pct = p.progress.total ? Math.round(p.progress.done / p.progress.total * 100) : 0;
    const editGoal = h("input", { value: p.goal || "", placeholder: lang === "th" ? "เป้าหมาย" : "Goal", maxlength: 500 });
    const editDeadline = h("input", { type: "date", value: p.deadline || "", "aria-label": lang === "th" ? "กำหนดส่ง" : "Deadline" });
    const editNext = h("input", { value: p.next_step || "", placeholder: lang === "th" ? "ขั้นต่อไป" : "Next step", maxlength: 300 });
    const kind = h("select", { "aria-label": lang === "th" ? "ประเภทรายการ" : "Item type" },
      [["milestone", "Milestone"], ["blocker", "Blocker"], ["note", "Note"], ["decision", "Decision"]].map(([value, label]) => h("option", { value, text: label })));
    const detail = h("input", { placeholder: lang === "th" ? "อธิบายรายการ" : "Describe a milestone, blocker, note, or decision", maxlength: 500 });
    const itemDue = h("input", { type: "date", "aria-label": lang === "th" ? "กำหนดหมุดหมาย" : "Milestone due date" });
    const itemRow = (x) => h("div", { class: "row" },
      h("span", { class: "tag " + (x.done ? "ok" : x.kind === "blocker" ? "bad" : ""), text: x.kind }),
      h("span", { class: "grow", text: x.text }), x.due ? h("span", { class: "dim", text: x.due }) : null,
      ["milestone", "blocker"].includes(x.kind) && !x.done ? h("button", { onclick: async () => { const r = await post(`/projects/${p.id}/items/${x.id}/complete`); if (r.ok) vProjects(); else toast(r.error); }, text: x.kind === "blocker" ? "Resolved" : t("done") }) : null);
    v.append(panel(p.name,
      h("div", { class: "project-meta" },
        p.deadline ? h("span", { class: "tag", text: (lang === "th" ? "กำหนด " : "Due ") + p.deadline }) : null,
        h("span", { class: "dim", text: `${p.progress.done}/${p.progress.total} ${lang === "th" ? "หมุดหมาย" : "milestones"}` })),
      h("div", { class: "bar project-progress" }, h("i", { style: `width:${pct}%` })),
      p.goal ? h("p", null, h("b", { text: lang === "th" ? "เป้าหมาย: " : "Goal: " }), h("span", { text: p.goal })) : null,
      p.next_step ? h("p", null, h("b", { text: lang === "th" ? "ขั้นต่อไป: " : "Next step: " }), h("span", { text: p.next_step })) : null,
      h("h4", { text: lang === "th" ? "สิ่งที่ติดขัด" : "Blockers" }), ...(p.blockers.length ? p.blockers.map(itemRow) : [h("p", { class: "dim", text: lang === "th" ? "ไม่มีสิ่งที่ติดขัด" : "No blockers" })]),
      h("h4", { text: lang === "th" ? "หมุดหมาย" : "Milestones" }), ...(p.milestones.length ? p.milestones.map(itemRow) : [h("p", { class: "dim", text: lang === "th" ? "ยังไม่มีหมุดหมาย" : "No milestones yet" })]),
      p.recent.length ? h("details", null, h("summary", { text: lang === "th" ? "บันทึกและการตัดสินใจ" : "Notes and decisions" }), ...p.recent.map(itemRow)) : null,
      h("div", { class: "project-add" }, kind, detail, itemDue,
        h("button", { onclick: async () => { const r = await act(`/projects/${p.id}/items`, { kind: kind.value, text: detail.value, due: itemDue.value }); if (r.ok) vProjects(); }, text: t("add") })),
      h("details", { class: "project-edit" }, h("summary", { text: lang === "th" ? "แก้ข้อมูลโปรเจกต์" : "Edit project details" }),
        h("div", { class: "project-form" }, editGoal, editDeadline, editNext),
        h("button", { onclick: async () => { const r = await api(`/projects/${p.id}`, { method: "PUT", body: { goal: editGoal.value, deadline: editDeadline.value, next_step: editNext.value } }); if (r.ok) vProjects(); else toast(r.error); }, text: t("save") })),
      h("button", { class: "bad project-close", onclick: async () => { if (confirm(lang === "th" ? "ปิดโปรเจกต์นี้?" : "Close this project?")) { const r = await post(`/projects/${p.id}/close`); if (r.ok) vProjects(); else toast(r.error); } }, text: lang === "th" ? "ปิดโปรเจกต์" : "Close project" })));
  }
}
async function renderTasks(v, serial) {
  const dr = await api("/drafts"); if (serial !== viewSerial) return;
  if (dr.drafts.length) v.append(draftsPanel(dr.drafts, vManage));
  const d = await api("/tasks"); const title = h("input", { placeholder: t("task_title") }), due = h("input", { placeholder: t("task_due") });
  if (serial !== viewSerial) return;
  const open = d.tasks.filter(x => !x.done), overdue = open.filter(x => x.due && new Date(x.due.replace(" ", "T")) < new Date());
  v.append(h("div", { class: "page-summary" }, h("strong", { text: String(open.length) }), h("span", { text: lang === "th" ? "งานค้าง" : "open tasks" }),
    h("strong", { text: String(overdue.length) }), h("span", { text: lang === "th" ? "เลยกำหนด" : "overdue" }),
    h("strong", { text: String(d.reminders.length) }), h("span", { text: lang === "th" ? "การเตือน" : "reminders" })));
  v.append(panel(t("task_add"), title, h("div", { style: "height:6px" }), due, h("p", null, h("button", { class: "pri", onclick: async () => { const r = await act("/tasks", { title: title.value, due: due.value }); if (r.ok) vManage(); }, text: t("add") }))));
  v.append(panel(t("tasks_title"), ...d.tasks.map(x => h("div", { class: "row" }, h("span", { class: "grow", style: x.done ? "text-decoration:line-through;opacity:.5" : "", text: x.title }),
    h("span", { class: "tag " + (x.done ? "ok" : overdue.some(y => y.id === x.id) ? "bad" : ""), text: x.done ? t("done") : x.due || (lang === "th" ? "ไม่มีกำหนด" : "No due date") }),
    x.done ? null : h("button", { onclick: async () => { await post("/tasks/" + x.id + "/complete"); vManage(); }, text: t("done") })))));
  const rt = h("input", { placeholder: t("rem_text") }), rw = h("input", { placeholder: t("rem_when") });
  v.append(panel(t("reminders_title"), ...d.reminders.map(r => h("div", { class: "row" }, h("span", { class: "grow", text: r.text }), h("span", { class: "dim", text: r.due }))), rt, h("div", { style: "height:6px" }), rw,
    h("p", null, h("button", { onclick: async () => { const r = await act("/reminders", { text: rt.value, when: rw.value }); if (r.ok) vManage(); }, text: t("add") }))));
}

// ---------- management hub: Tasks, Projects, Calendar, Newspaper (visible tabs saved on this device) ----------
const MGMT_TABS = [["tasks", () => t("sub_tasks")], ["projects", () => (lang === "th" ? "โปรเจกต์" : "Projects")],
  ["calendar", () => (lang === "th" ? "ปฏิทิน" : "Calendar")], ["news", () => (lang === "th" ? "ข่าว" : "Newspaper")]];
function mgmtHidden() {
  try { const list = JSON.parse(localStorage.getItem("nano.mgmt.hidden") || "null"); return Array.isArray(list) ? list : ["news"]; } catch (e) { return ["news"]; }
}
function setMgmtHidden(list) { try { localStorage.setItem("nano.mgmt.hidden", JSON.stringify(list)); } catch (e) {} }
async function vManage() {
  const v = clear(), serial = viewSerial;
  const hidden = mgmtHidden();
  const visible = MGMT_TABS.filter(([k]) => !hidden.includes(k));
  let cur = sub.manage || "tasks";
  if (!visible.some(([k]) => k === cur)) cur = visible.length ? visible[0][0] : "";
  sub.manage = cur;
  v.append(viewHeading(lang === "th" ? "จัดการ" : "Management", lang === "th" ? "งาน โปรเจกต์ ปฏิทิน และข่าว ในที่เดียว" : "Tasks, projects, calendar, and news in one place.", 3));
  v.append(h("div", { class: "mgmt-bar" },
    chips(visible.map(([k, label]) => [k, label()]), cur, k => { sub.manage = k; vManage(); }),
    h("button", { class: "tab-prefs", "aria-expanded": sub.managePrefs ? "true" : "false", onclick: () => { sub.managePrefs = !sub.managePrefs; vManage(); } },
      lang === "th" ? "ปรับแต่งแท็บ" : "Customize tabs")));
  if (sub.managePrefs) v.append(panel(lang === "th" ? "แท็บที่แสดง" : "Visible tabs",
    ...MGMT_TABS.map(([k, label]) => h("label", { class: "pref-row" },
      h("input", { type: "checkbox", role: "switch", ...(hidden.includes(k) ? {} : { checked: true }), onchange: e => {
        const next = e.target.checked ? hidden.filter(x => x !== k) : [...hidden, k];
        if (next.length >= MGMT_TABS.length) { e.target.checked = true; toast(lang === "th" ? "ต้องแสดงอย่างน้อยหนึ่งแท็บ" : "Keep at least one tab visible"); return; }
        setMgmtHidden(next); vManage(); } }),
      h("span", { text: label() }))),
    h("p", { class: "dim", text: lang === "th" ? "การตั้งค่านี้เก็บในเครื่องนี้" : "Saved on this device." })));
  if (cur === "tasks") await renderTasks(v, serial);
  else if (cur === "projects") await renderProjects(v, serial);
  else if (cur === "calendar") await vCalendar(v, serial);
  else if (cur === "news") v.append(newsPanel());
  else v.append(panel(lang === "th" ? "ไม่มีแท็บที่แสดง" : "No tabs shown", h("p", { class: "dim", text: lang === "th" ? "เปิดแท็บอย่างน้อยหนึ่งแท็บใน แสดง/ซ่อนแท็บ" : "Turn at least one tab back on under Show or hide tabs." })));
}

async function vCalendar(v, serial) {
  const [tasksData, projectsData] = await Promise.all([api("/tasks"), api("/projects")]);
  if (serial !== viewSerial) return;
  const events = [];
  for (const task of tasksData.tasks) if (task.due && !task.done) events.push({ date: task.due.slice(0, 10), label: task.title, time: task.due.slice(11), kind: "task" });
  for (const rem of tasksData.reminders) if (rem.due) events.push({ date: rem.due.slice(0, 10), label: rem.text, time: rem.due.slice(11), kind: "reminder" });
  for (const p of projectsData.items || []) {
    if (p.deadline) events.push({ date: p.deadline, label: p.name, time: "", kind: "project" });
    for (const m of p.milestones) if (m.due && !m.done) events.push({ date: m.due, label: m.text, time: "", kind: "milestone" });
  }
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const chosen = sub.calendarDate ? new Date(sub.calendarDate + "T12:00:00") : new Date();
  const mode = sub.calendarView || "week";
  const advance = delta => { const next = new Date(chosen); if (mode === "month") next.setMonth(next.getMonth() + delta); else next.setDate(next.getDate() + delta * (mode === "week" ? 7 : 1)); sub.calendarDate = iso(next); vManage(); };
  const start = new Date(chosen); if (mode === "month") { start.setDate(1); } start.setDate(start.getDate() - (start.getDay() + 6) % 7);
  const days = mode === "day" ? [chosen] : Array.from({ length: mode === "month" ? 42 : 7 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d; });
  const title = mode === "month" ? chosen.toLocaleDateString(lang === "th" ? "th-TH" : undefined, { month: "long", year: "numeric" })
    : mode === "day" ? chosen.toLocaleDateString(lang === "th" ? "th-TH" : undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" })
    : `${days[0].toLocaleDateString(lang === "th" ? "th-TH" : undefined, { day: "numeric", month: "short" })} – ${days[6].toLocaleDateString(lang === "th" ? "th-TH" : undefined, { day: "numeric", month: "short", year: "numeric" })}`;
  v.append(panel(lang === "th" ? "ปฏิทิน" : "Calendar",
    h("div", { class: "calendar-toolbar" }, chips([["day", lang === "th" ? "วัน" : "Day"], ["week", lang === "th" ? "สัปดาห์" : "Week"], ["month", lang === "th" ? "เดือน" : "Month"]], mode, x => { sub.calendarView = x; vManage(); }),
      h("div", { class: "calendar-nav" }, h("button", { onclick: () => advance(-1), text: "‹" }),
        h("button", { onclick: () => { sub.calendarDate = iso(new Date()); vManage(); }, text: lang === "th" ? "วันนี้" : "Today" }),
        h("button", { onclick: () => advance(1), text: "›" }))),
    h("h3", { class: "calendar-title", text: title }),
    h("p", { class: "dim", text: lang === "th" ? "แสดงงาน การเตือน และหมุดหมายโปรเจกต์ที่บันทึกไว้ใน Nano Agent" : "Shows Nano Agent tasks, reminders, and project milestones." }),
    h("div", { class: "calendar-grid calendar-" + mode }, days.map(d => {
      const dayEvents = events.filter(e => e.date === iso(d)).sort((a, b) => a.time.localeCompare(b.time));
      return h("div", { class: "calendar-day" + (iso(d) === iso(new Date()) ? " today" : "") + (mode === "month" && d.getMonth() !== chosen.getMonth() ? " outside" : "") },
        h("strong", { text: d.toLocaleDateString(lang === "th" ? "th-TH" : undefined, { weekday: "short", day: "numeric" }) }),
        ...dayEvents.map(e => h("div", { class: "calendar-event " + e.kind }, h("b", { text: e.time }), h("span", { text: e.label }))));
    }))));
}

// ---------- mind: memory, skills, learning ----------
async function vMind() {
  const v = clear(); const fixed = ["learning", "know"].includes(tab) ? tab : null;
  const cur = fixed || sub.mind || "learning";
  v.append(viewHeading(t("sub_" + cur), lang === "th" ? "ความจำ ทักษะ และการเรียนรู้" : "Memory, skills, and learning", cur === "skills" ? 6 : 7));
  if (!fixed) v.append(chips([["learning", t("sub_learning")], ["know", t("sub_know")]], cur, k => { sub.mind = k; vMind(); }));
  ({ memory: mMemory, skills: mSkills, learning: mLearning, know: mKnow })[cur](v);
}
async function mMemory(v) {
  const serial = viewSerial, d = await api("/memory"); if (serial !== viewSerial) return;
  const inp = h("input", { placeholder: t("memory_add_ph") });
  const overview = d.overview || {}, kinds = ["fact", "rule", "lesson"];
  v.append(h("div", { class: "page-summary" }, h("strong", { text: String(d.items.length) }), h("span", { text: lang === "th" ? "ความจำทั้งหมด" : "memories" }),
    ...kinds.flatMap(k => [h("strong", { text: String(overview[k] || 0) }), h("span", { text: k })])));
  const kind = h("select", { "aria-label": lang === "th" ? "ประเภทความจำ" : "Memory type" },
    kinds.map(k => h("option", { value: k, text: k })));
  v.append(chips([["text", lang === "th" ? "ข้อความ" : "Text"], ["graph", lang === "th" ? "กราฟ" : "Graph"]], sub.memoryView || "text", x => { sub.memoryView = x; vCustom(); }));
  v.append(panel(t("memory_add"), h("div", { class: "memory-add" }, kind, inp),
    h("p", null, h("button", { class: "pri", onclick: async () => { const r = await act("/memory", { text: inp.value, kind: kind.value }); if (r.ok) vCustom(); }, text: t("add") }))));
  if (sub.memoryView === "graph") {
    const graph = sv("svg", { class: "memory-graph", viewBox: "0 0 640 340", role: "img", "aria-label": lang === "th" ? "กราฟความจำ" : "Memory graph" });
    const center = [320, 166], positions = { fact: [155, 80], rule: [485, 80], lesson: [320, 274] };
    const textNode = (x, y, value, css) => { const el = sv("text", { x, y, "text-anchor": "middle", class: css }); el.textContent = value; return el; };
    for (const k of kinds) { const [x, y] = positions[k], rows = d.items.filter(m => m.kind === k);
      const node = sv("circle", { cx: x, cy: y, r: 35, class: "memory-node memory-" + k + ((sub.memoryKind || "all") === k ? " selected" : "") });
      node.addEventListener("click", () => { sub.memoryKind = k; vCustom(); });
      graph.append(sv("line", { x1: center[0], y1: center[1], x2: x, y2: y, class: "memory-link" }),
        node, textNode(x, y + 7, String(rows.length), "memory-count"),
        textNode(x, y + 56, k.toUpperCase(), "memory-label"));
    }
    graph.append(sv("circle", { cx: center[0], cy: center[1], r: 42, class: "memory-core" }),
      textNode(center[0], center[1] + 6, lang === "th" ? "คุณ" : "YOU", "memory-count"));
    v.append(panel(lang === "th" ? "แผนที่ความจำ" : "Memory map", graph,
      h("p", { class: "dim", text: lang === "th" ? "ความจำแบ่งเป็นข้อเท็จจริง กฎ และบทเรียน" : "Memories are grouped as facts, rules, and lessons." })));
  }
  v.append(chips([["all", lang === "th" ? "ทั้งหมด" : "All"], ...kinds.map(k => [k, k])], sub.memoryKind || "all", x => { sub.memoryKind = x; vCustom(); }));
  const shown = d.items.filter(m => (sub.memoryKind || "all") === "all" || m.kind === sub.memoryKind);
  v.append(panel(t("memory_title"), shown.length ? shown.map(m => h("div", { class: "row" }, h("span", { class: "tag", text: m.kind }), h("span", { class: "grow", text: m.text }), h("span", { class: "dim", text: m.source }),
    h("button", { class: "bad", onclick: async () => { if (confirm(lang === "th" ? "ลืมรายการนี้?" : "Forget this memory?")) { await del("/memory/" + m.id); vCustom(); } }, text: t("delete") }))) : h("p", { class: "dim", text: t("memory_none") })));
}
async function mSkills(v) {
  const serial = viewSerial, d = await api("/skills"); if (serial !== viewSerial) return;
  const txt = h("textarea", { placeholder: t("skill_import_ph") }), url = h("input", { placeholder: "https://github.com/owner/repo" });
  const enabled = d.skills.filter(s => s.enabled && !s.pending).length, pending = d.skills.filter(s => s.pending).length;
  v.append(h("div", { class: "page-summary" }, h("strong", { text: String(enabled) }), h("span", { text: lang === "th" ? "ทักษะที่เปิด" : "enabled skills" }),
    h("strong", { text: String(pending) }), h("span", { text: lang === "th" ? "รอตรวจ" : "awaiting review" })));
  const skillRow = s => h("div", { class: "row" }, h("span", { class: "grow" }, h("b", { text: s.name }), h("div", { class: "dim", text: s.description }),
    h("small", { class: "dim", text: lang === "th" ? `แหล่งที่มา: ${s.source}` : `Source: ${s.source}` })),
    h("span", { class: "tag " + (s.pending ? "warn" : s.enabled ? "ok" : ""), text: s.pending ? t("skill_pending") : s.enabled ? t("on") : t("off") }), h("button", { onclick: () => skillSheet(s), text: t("open") }));
  if (pending) v.append(panel(lang === "th" ? "รอคุณตรวจก่อนเปิดใช้" : "Review before enabling", d.skills.filter(s => s.pending).map(skillRow)));
  v.append(panel(t("skills_title"), d.skills.some(s => !s.pending) ? d.skills.filter(s => !s.pending).map(skillRow) : h("p", { class: "dim", text: t("skills_none") })));
  const skName = h("input", { placeholder: lang === "th" ? "ชื่อทักษะ" : "Skill name" }), skDesc = h("input", { placeholder: lang === "th" ? "ทักษะนี้ทำอะไร" : "What this skill does" }), skBody = h("textarea", { placeholder: lang === "th" ? "คำแนะนำสำหรับ AI" : "Instructions for the assistant" });
  v.append(panel(lang === "th" ? "สร้างทักษะ" : "Create a skill", skName, skDesc, skBody,
    h("button", { class: "pri", onclick: async () => { const r = await act("/skills", { name: skName.value, description: skDesc.value, body: skBody.value }); if (r.ok) vCustom(); }, text: lang === "th" ? "สร้าง" : "Create" })));
  v.append(panel(t("skill_import"), h("p", { class: "dim", text: t("skill_import_note") }), url, h("p", null, h("button", { onclick: async () => { const r = await post("/skills/import", { kind: "url", url: url.value }); toast(JSON.stringify((r.results || []).map(x => x.ok ? x.name : x.error))); vCustom(); }, text: t("import_github") })),
    txt, h("p", null, h("button", { onclick: async () => { const r = await post("/skills/import", { kind: "text", text: txt.value }); toast(JSON.stringify((r.results || []).map(x => x.ok ? x.name : x.error))); vCustom(); }, text: t("import_text") }))));
}
async function skillSheet(s) {
  const r = await api("/skills/" + encodeURIComponent(s.name)); const v = clear(); const ta = h("textarea", { style: "min-height:260px" }); ta.value = r.text || "";
  const ack = h("input", { type: "checkbox", style: "width:auto" });
  v.append(panel(s.name, r.review ? h("div", null, h("span", { class: "tag " + (r.review.verdict === "ok" ? "ok" : "bad"), text: r.review.verdict }), h("pre", { text: r.review.findings.join("\n") || t("review_clean") }),
      h("label", null, ack, " " + t("review_ack"))) : null,
    r.files?.length ? h("p", { class: "dim", text: (lang === "th" ? "ไฟล์: " : "Files: ") + r.files.join(", ") }) : null, ta,
    h("p", null, !r.pending ? h("button", { class: "pri", onclick: async () => { const b = ta.value.split(/^---\s*$/m); await api("/skills/" + encodeURIComponent(s.name), { method: "PUT", body: { body: (b[2] || ta.value).trim() } }); toast(t("saved")); }, text: t("save") }) : null,
      h("button", { onclick: async () => { const x = await post("/skills/" + encodeURIComponent(s.name) + "/toggle", { enabled: r.pending ? true : !s.enabled, ack: ack.checked }); if (x.ok === false) toast(x.error); else { sub.mind = "skills"; vCustom(); } }, text: r.pending ? t("skill_enable") : (s.enabled ? t("skill_disable") : t("skill_enable")) }),
      h("button", { class: "bad", onclick: async () => { if (confirm(lang === "th" ? "ลบทักษะนี้?" : "Delete this skill?")) { await del("/skills/" + encodeURIComponent(s.name)); vCustom(); } }, text: t("delete") }), h("button", { onclick: vMind, text: t("back") }))));
}
async function mLearning(v) {
  const d = await api("/learning");
  if (d.week_note) v.append(panel(t("week_note"), h("p", { text: d.week_note.note || t("week_nothing") })));
  if (d.proposals.length) v.append(panel(t("proposals"), d.proposals.map(p => h("div", { class: "row" }, h("span", { class: "grow", text: p.scope + "." + p.key + " = " + JSON.stringify(p.value) + (p.reason ? " — " + p.reason : "") }),
    h("button", { class: "pri", onclick: async () => { await post("/learning/proposal", { id: p.id, accept: true }); vMind(); }, text: t("use") }), h("button", { onclick: async () => { await post("/learning/proposal", { id: p.id, accept: false }); vMind(); }, text: t("reject") })))));
  v.append(panel(t("settings_in_effect"), Object.entries(d.settings).map(([k, val]) => { const sc = d.schema[k]; let el;
    if (Array.isArray(sc) && typeof val === "string") { el = h("select", { onchange: async e => { await post("/learning/pref", { setting: k, value: e.target.value }); applyUi({ [k]: e.target.value }); } }, sc.map(o => h("option", { value: o, selected: o === val ? "" : null, text: o }))); }
    else el = h("span", { class: "dim", text: JSON.stringify(val) });
    return h("div", { class: "row" }, h("span", { class: "grow", text: k }), el, h("button", { onclick: async () => { await post("/learning/restore", { setting: k }); vMind(); }, text: t("default") })); })));
  v.append(panel(t("level_title"), h("select", { onchange: async e => { await post("/companion/level", { level: e.target.value }); toast(t("saved")); } }, ["assistant", "buddy", "friend"].map(l => h("option", { value: l, selected: l === d.level ? "" : null, text: t("level_" + l) })))));
  v.append(panel(t("log_title"), d.log.length ? d.log.map(l => h("div", { class: "row" }, h("span", { class: "tag", text: l.kind }), h("span", { class: "grow", text: l.title + (l.reason ? " — " + l.reason : "") }), h("span", { class: "dim", text: when(l.ts) }),
    l.status === "done" ? h("button", { onclick: async () => { const r = await post("/learning/undo", { id: l.id }); toast(r.ok ? t("undone") : r.error); vMind(); }, text: t("undo") }) : h("span", { class: "tag", text: t("undone") }))) : h("p", { class: "dim", text: t("log_none") })));
  const pt = await api("/patches");
  v.append(panel(t("patches_title"), h("p", { class: "dim", text: t("patches_note") }), pt.patches.length ? pt.patches.map(p => h("div", { class: "row" }, h("span", { class: "tag " + (p.status === "ready" ? "warn" : p.status === "applied" ? "ok" : ""), text: p.status }), h("span", { class: "grow", text: p.title }),
    h("button", { onclick: () => patchSheet(p.id), text: t("open") }))) : h("p", { class: "dim", text: t("patches_none") })));
}
async function patchSheet(id) {
  const p = await api("/patches/" + id), v = clear(), tr = JSON.parse(p.test_result || "{}");
  v.append(panel(p.title, h("p", { text: p.summary }), h("p", null, h("span", { class: "tag " + (tr.ok ? "ok" : "bad"), text: (tr.ok ? "tests ok: " : "tests failed: ") + (tr.detail || "") })), h("pre", { text: p.diff }),
    h("p", null, p.status === "ready" ? h("button", { class: "pri", onclick: async () => { const r = await post("/patches/" + id + "/approve"); toast(r.ok ? t("patch_applied") : r.error); vMind(); }, text: t("patch_approve") }) : null,
      p.status === "ready" || p.status === "failed" ? h("button", { class: "bad", onclick: async () => { await post("/patches/" + id + "/reject"); vMind(); }, text: t("reject") }) : null, h("button", { onclick: vMind, text: t("back") }))));
}
async function mKnow(v) {
  const d = await api("/learning");
  v.append(panel(t("know_title"), h("p", { class: "dim", text: t("know_note") }), d.traits.length ? d.traits.map(tr => { const val = h("input", { value: tr.value });
    return h("div", { class: "row" }, h("span", { class: "tag " + (tr.used ? "ok" : "warn"), text: tr.used ? t("know_used") : t("know_guess") }), h("b", { text: tr.name }), h("div", { class: "grow" }, val, h("div", { class: "dim", text: `${tr.reason} · ${tr.evidence}/${tr.needed} · ${Math.round(tr.confidence * 100)}%` })),
      h("button", { onclick: async () => { await post("/usermodel/correct", { name: tr.name, value: val.value }); vMind(); }, text: t("correct") }), h("button", { class: "bad", onclick: async () => { await del("/usermodel/" + tr.name); vMind(); }, text: t("delete") })); }) : h("p", { class: "dim", text: t("know_none") })));
}

// ---------- work: activity, automations, system ----------
async function vWork() {
  const v = clear(), serial = viewSerial; const fixed = ({ automation: "auto", activity: "activity" })[tab];
  const cur = fixed || sub.work || "activity";
  v.append(viewHeading(t("sub_" + cur), lang === "th" ? "กิจกรรม ระบบอัตโนมัติ และสถานะ" : "Activity, automations, and system status", 5));
  if (!fixed) v.append(chips([["activity", t("sub_activity")], ["auto", t("sub_auto")]], cur, k => { sub.work = k; vWork(); }));
  if (cur === "activity") { const a = await api("/activity"); if (serial !== viewSerial) return; const row = x => h("div", { class: "row" }, h("span", { class: "tag " + (x.status === "done" ? "ok" : x.status === "failed" ? "bad" : "warn"), text: x.status }), h("span", { class: "grow" }, h("b", { text: x.title }), x.steps.length ? h("div", { class: "dim", text: x.steps.slice(-3).map(s => s.text).join(" · ") }) : null), h("span", { class: "dim", text: Math.round(x.secs) + "s" }));
    v.append(panel(t("running_title"), a.running.length ? a.running.map(row) : h("p", { class: "dim", text: t("work_idle") })), panel(t("recent_title"), a.done.map(row))); }
  if (cur === "auto") { const a = await api("/automations"); if (serial !== viewSerial) return; const nm = h("input", { placeholder: t("auto_name") }), pr = h("textarea", { placeholder: t("auto_prompt") });
    const templates = [["custom", "Custom", "", ""], ["reminder", "Reminder", "Reminder", "Remind me about: "],
      ["research", "Research", "Research", "Research this topic and summarize the findings: "],
      ["summary", "Daily summary", "Daily summary", "Summarize my open tasks, reminders, and projects."],
      ["project", "Project report", "Project report", "Summarize progress, milestones, and blockers in my projects."]];
    const template = h("select", { "aria-label": lang === "th" ? "ชนิดระบบอัตโนมัติ" : "Automation template" },
      templates.map(([value, label]) => h("option", { value, text: label })));
    template.addEventListener("change", () => { const found = templates.find(x => x[0] === template.value); if (found && found[0] !== "custom") { nm.value = found[2]; pr.value = found[3]; } });
    const frequency = h("select", { "aria-label": lang === "th" ? "ความถี่" : "Frequency" },
      h("option", { value: "daily", text: lang === "th" ? "ทุกวัน" : "Daily" }), h("option", { value: "weekly", text: lang === "th" ? "ทุกสัปดาห์" : "Weekly" }));
    const day = h("select", { "aria-label": lang === "th" ? "วัน" : "Day of week" },
      ...["mon", "tue", "wed", "thu", "fri", "sat", "sun"].map(d => h("option", { value: d, text: d.toUpperCase() })));
    const at = h("input", { type: "time", value: "08:00", "aria-label": lang === "th" ? "เวลา" : "Time" });
    frequency.addEventListener("change", () => { day.hidden = frequency.value !== "weekly"; }); day.hidden = true;
    const scheduleText = x => x.schedule.daily ? (lang === "th" ? "ทุกวัน " : "Daily ") + x.schedule.daily : x.schedule.weekly ? x.schedule.weekly : JSON.stringify(x.schedule);
    v.append(h("div", { class: "page-summary" }, h("strong", { text: String(a.items.filter(x => x.enabled).length) }), h("span", { text: lang === "th" ? "ระบบที่เปิดอยู่" : "active automations" }),
      h("strong", { text: String(a.items.length) }), h("span", { text: lang === "th" ? "ทั้งหมด" : "total" }),
      h("button", { class: "pri", onclick: () => { nm.focus(); nm.scrollIntoView({ block: "center" }); }, text: lang === "th" ? "สร้างระบบอัตโนมัติใหม่" : "New automation" })),
      panel(t("auto_title"), a.items.length ? a.items.map(x => h("div", { class: "row" }, h("span", { class: "tag " + (x.enabled ? "ok" : ""), text: x.enabled ? t("on") : t("off") }),
      h("span", { class: "grow" }, h("b", { text: x.name }), h("div", { class: "dim", text: scheduleText(x) + (x.next_run && x.enabled ? " · Next " + when(x.next_run) : "") + (x.last_status ? " · " + x.last_status : "") })),
      h("button", { onclick: async () => { await post("/automations/" + x.id + "/toggle", { enabled: !x.enabled }); vWork(); }, text: x.enabled ? t("pause") : t("resume") }), h("button", { onclick: async () => { const r = await post("/automations/" + x.id + "/run"); toast(r.status || r.error); }, text: t("run_now") }),
      x.builtin ? null : h("button", { class: "bad", onclick: async () => { if (confirm(lang === "th" ? "ลบระบบนี้?" : "Delete this automation?")) { await del("/automations/" + x.id); vWork(); } }, text: t("delete") }))) : h("div", { class: "jv-empty-box" }, ico("skills", "ico ico-lg"),
        h("p", { class: "jv-note", text: lang === "th" ? "ยังไม่มีระบบอัตโนมัติ สร้างหนึ่งรายการเพื่อให้ทำงานตามเวลาที่ตั้งไว้" : "No automations yet. Create one to run a prompt on a schedule." }),
        h("button", { class: "pri", onclick: () => { nm.focus(); nm.scrollIntoView({ block: "center" }); }, text: lang === "th" ? "สร้างระบบอัตโนมัติใหม่" : "New automation" }))),
      panel(t("auto_new"), template, nm, pr, h("div", { class: "auto-schedule" }, frequency, day, at),
        h("p", { class: "dim", text: lang === "th" ? "ระบบจะทำงานตามเวลาในเขตเวลาที่ตั้งไว้" : "Runs in your configured time zone." }),
        h("button", { class: "pri", onclick: async () => { const schedule = frequency.value === "weekly" ? { weekly: `${day.value} ${at.value}` } : { daily: at.value }; const r = await act("/automations", { name: nm.value, prompt: pr.value, schedule }); if (r.ok) vWork(); }, text: t("add") }))); }
}

// ---------- customization hub, appearance, agents, system, settings ----------
const ACCENT_HEX = { orange: "#ff6a00", blue: "#38bdf8", violet: "#a78bfa", green: "#34d399", cyan: "#38d6ff", rose: "#fb7185" };
const CUSTOM_TABS = () => [["memory", t("sub_memory")], ["skills", t("sub_skills")], ["agents", lang === "th" ? "เอเจนต์" : "Agents"]];
// Old #tab= deep links redirect into the hub that now owns the page.
const REDIRECT = { projects: ["manage", "projects"], tasks: ["manage", "tasks"], calendar: ["manage", "calendar"], memory: ["customization", "memory"], skills: ["customization", "skills"], mind: ["customization", "memory"] };
function routeFromHash(hp) {
  const want = hp.get("tab"), sec = hp.get("sub");
  if (!want) return;
  if (REDIRECT[want]) {
    const [hub, part] = REDIRECT[want];
    tab = hub;
    sub[hub === "manage" ? "manage" : "custom"] = sec || part;
  } else if (TABS.includes(want)) { tab = want; if (sec) sub[want] = sec; }
}
async function vCustom() {
  const v = clear(), serial = viewSerial;
  const cur = tab === "skills" ? "skills" : tab === "memory" ? "memory" : (sub.custom || "memory");
  sub.custom = cur;
  v.append(viewHeading(lang === "th" ? "ปรับแต่ง" : "Customization", lang === "th" ? "ความจำ ทักษะ รูปลักษณ์ และเอเจนต์" : "Memory, skills, appearance, and agents", 6),
    chips(CUSTOM_TABS(), cur, k => { sub.custom = k; go("customization"); }));
  if (cur === "memory") await mMemory(v);
  else if (cur === "skills") await mSkills(v);
  else agentsPanel(v);
  if (serial !== viewSerial) return;
}
function appearancePanel(v) {
  const baseTheme = currentBaseTheme();
  const themes = [
    ["light", lang === "th" ? "สว่าง (Light)" : "Light", lang === "th" ? "พื้นหลังสว่าง สะอาดตา เหมาะกับกลางวัน" : "Clean luminous workspace for daytime focus"],
    ["dark", lang === "th" ? "มืด (Dark)" : "Dark", lang === "th" ? "พื้นหลังเข้ม สบายตาในที่แสงน้อย" : "Deep slate workspace for low-light comfort"]
  ];
  const curAccent = document.documentElement.dataset.accent || "orange";
  v.append(panel(lang === "th" ? "รูปแบบหน้าจอ" : "Appearance",
    h("p", { class: "dim", text: lang === "th" ? "เลือกโหมดสว่างหรือมืด เปลี่ยนได้ตลอดเวลา" : "Choose Light or Dark appearance. Saved to your preferences." }),
    h("div", { class: "theme-options" }, themes.map(([key, title, detail]) => h("button", {
      class: "theme-option theme-option-" + key + (baseTheme === key ? " selected" : ""),
      "aria-pressed": baseTheme === key ? "true" : "false",
      onclick: () => setTheme(key)
    }, h("span", { class: "theme-preview" }, h("i"), h("i"), h("i")), h("strong", { text: title }), h("small", { text: detail })))),
    h("div", { class: "accent-row" },
      h("span", { class: "dim", text: lang === "th" ? "สีเน้น:" : "Accent:" }),
      ...Object.entries(ACCENT_HEX).map(([k, hex]) => h("button", {
        class: "accent-dot" + (curAccent === k ? " on" : ""),
        style: `background:${hex}`,
        title: k,
        "aria-label": k,
        onclick: async () => {
          applyUi({ "ui.accent": k });
          vSettings();
          try { const r = await post("/learning/pref", { setting: "ui.accent", value: k }); if (r.ok && ME.prefs) ME.prefs["ui.accent"] = k; } catch (e) {}
        }
      }))),
    h("p", { class: "dim", text: lang === "th" ? "มาสคอต: n (ค่าเริ่มต้น) มาสคอตอื่นจะเพิ่มในภายหลัง" : "Mascot: n (default). More mascots will be added here later." })));
}
function agentsPanel(v) {
  v.append(panel(lang === "th" ? "เอเจนต์" : "Agents",
    h("div", { class: "banner" }, lang === "th" ? "ยังไม่มีเอเจนต์ที่เชื่อมต่อ ไม่มีอะไรกำลังทำงาน" : "No agents are connected. Nothing is running."),
    h("div", { class: "row" }, h("span", { class: "agent-av", "data-mascot": "main" }), h("span", { class: "grow", text: lang === "th" ? "เอเจนต์หลัก" : "Main agent" }), h("span", { class: "tag ok", text: lang === "th" ? "พร้อม" : "Ready" })),
    h("div", { class: "agent-slots" }, [0, 1, 2].map(() => h("span", { class: "agent-letter slot", "aria-hidden": "true" }, subSlotNode())))));
}
function newsPanel() {
  return panel(lang === "th" ? "ข่าว" : "Newspaper",
    h("div", { class: "jv-empty-box" }, ico("news", "ico ico-lg"),
      h("p", { class: "jv-note", text: lang === "th" ? "ยังไม่ได้เชื่อมต่อ ยังไม่มีแหล่งข่าวที่ตั้งค่าไว้ใน nano Agent" : "Not connected yet. No news source is set up in nano Agent." })));
}
// ---------- system: device status + nano Agent status (real data only; missing values say so) ----------
async function vSystem() {
  const v = clear(), serial = viewSerial;
  const [s, act, sb] = await Promise.all([api("/system"), api("/activity"), api("/sandbox/status").catch(() => null)]);
  if (serial !== viewSerial) return;
  const i = s.info, cfg = sb ? (sb.config || {}) : {}, sup = sb ? (sb.supervisor || {}) : {};
  const na = lang === "th" ? "ไม่มีข้อมูล" : "Not available";
  const pct = x => x == null ? na : `${Math.round(x)}%`;
  const row = (k, val) => h("div", { class: "row" }, h("b", { class: "system-detail-label", text: k }), h("span", { class: "dim grow", text: val == null || val === "" ? na : String(val) }));
  v.append(viewHeading(lang === "th" ? "ระบบ" : "System", lang === "th" ? "สถานะเครื่องและ nano Agent" : "Device and nano Agent status", 5));
  v.append(panel(lang === "th" ? "สถานะเครื่อง" : "Device status",
    h("div", { class: "resource-grid" }, [["CPU", pct(i.cpu_pct)], ["RAM", pct(i.ram_pct)], ["Disk", pct(i.disk_pct)], ["Uptime", i.uptime_hours == null ? na : `${i.uptime_hours} h`]]
      .map(([n, val]) => h("div", { class: "resource-card" }, h("strong", { text: val }), h("span", { text: n })))),
    i.cpu_pct == null ? h("p", { class: "dim", text: t("system_psutil") }) : null,
    row(lang === "th" ? "เครื่อง" : "Machine", [i.host, i.os].filter(Boolean).join(" · ")),
    row("CPU", [i.cpu_name, i.cores ? `${i.cores} cores` : ""].filter(Boolean).join(" · ")),
    row("RAM", i.ram_total_gb ? `${i.ram_total_gb} GB` : null),
    row(lang === "th" ? "พื้นที่จัดเก็บ" : "Storage", i.disk_total_gb ? `${i.disk_total_gb} GB` : null),
    row("GPU", i.gpu ? i.gpu.name : (lang === "th" ? "ไม่พบ" : "Not detected"))));
  const last = (act.done || [])[0];
  v.append(panel(lang === "th" ? "สถานะ nano Agent" : "nano Agent status",
    row(lang === "th" ? "เวอร์ชัน" : "Version", i.version),
    row(lang === "th" ? "โมเดล" : "Model", ME.model),
    row(lang === "th" ? "ผู้ให้บริการ" : "Providers", Object.entries(s.providers || {}).map(([n, p]) => `${n} (${p.kind})`).join(", ")),
    row(lang === "th" ? "เกตเวย์" : "Gateway", lang === "th" ? "ตอบสนอง (คอนโซลเชื่อมต่ออยู่)" : "Responding (this console is connected)"),
    row(lang === "th" ? "ระดับ sandbox" : "Sandbox tier", sb ? cfg.tier : null),
    row(lang === "th" ? "สถานะสวิตช์หยุดฉุกเฉิน" : "Kill switch state", sb ? sup.state : null),
    row(lang === "th" ? "การรันล่าสุด" : "Last run", last ? `${last.title} · ${when(last.ts)}` : (lang === "th" ? "ยังไม่มี" : "None yet"))));
  const work = [...act.running, ...act.done.slice(0, 5)];
  v.append(panel(lang === "th" ? "งานเบื้องหลัง" : "Background work", work.length ? work.map(x =>
    h("details", { class: "system-activity" }, h("summary", null,
      h("span", { class: "tag " + (x.status === "done" ? "ok" : x.status === "failed" ? "bad" : "warn"), text: x.status }),
      h("b", { text: x.title })),
      h("p", { class: "dim", text: x.detail || (x.steps || []).map(step => step.text).join(" · ") || (lang === "th" ? "ยังไม่มีรายละเอียด" : "No details yet") })))
    : h("p", { class: "dim", text: lang === "th" ? "ตอนนี้ไม่มีงานเบื้องหลัง" : "No background work right now." })));
  v.append(panel(t("health_title"), s.health.map(c => h("div", { class: "row" }, h("span", { class: "tag " + (c.ok ? "ok" : "bad"), text: c.ok ? "OK" : "!" }), h("span", { class: "grow", text: c.name }), h("span", { class: "dim", text: c.detail })))));
}

// ---------- settings: profile, language, about ----------
async function vSettings() {
  const v = clear(); const name = h("input", { value: ME.owner_name || "" }), tz = h("input", { value: ME.timezone || "" });
  const lg = h("select", null, ["en", "th"].map(l => h("option", { value: l, selected: l === lang ? "" : null, text: l === "en" ? "English" : "ไทย" })));
  v.append(viewHeading(t("tab_settings"), lang === "th" ? "โปรไฟล์และภาษา" : "Profile, language, and about", 7),
    h("div", { class: "settings-shortcuts" },
      h("button", { onclick: () => go("learning"), text: t("sub_learning") }),
      h("button", { onclick: () => go("know"), text: t("sub_know") })));
  appearancePanel(v);
  v.append(panel(t("settings_title"), field(t("set_name"), name), field(t("set_tz"), tz), field(t("set_lang"), lg),
    h("p", null, h("button", { class: "pri", onclick: async () => { const r = await act("/settings", { owner_name: name.value, timezone: tz.value, language: lg.value }); if (r.ok) { toast(t("saved")); boot(); } }, text: t("save") }))));
  v.append(panel(lang === "th" ? "การแจ้งเตือน" : "Notifications",
    h("label", { class: "pref-row" },
      h("input", { type: "checkbox", role: "switch", ...(approvalNoticesOn() ? { checked: true } : {}), onchange: e => { try { localStorage.setItem("nano.notify.approvals", e.target.checked ? "on" : "off"); } catch (x) {} updateBellDot(); } }),
      h("span", { text: lang === "th" ? "แสดงจุดแจ้งเตือนเมื่อมีรายการรออนุมัติ (บนเครื่องนี้)" : "Show the bell dot when approvals are waiting (this device only)" })),
    h("p", { class: "dim", text: lang === "th" ? "ตอนนี้ไม่มีการส่งการแจ้งเตือนไปยังอุปกรณ์อื่น อีเมล หรือ LINE" : "No push, email or LINE notices are sent yet. This only controls the in-app dot." }),
    h("p", null, h("a", { href: "https://github.com/julachok20/nano-agent", target: "_blank", rel: "noopener noreferrer", text: lang === "th" ? "ที่เก็บโค้ด (Open Source)" : "Open Source repository" }))));
  v.append(panel(t("about_title"), h("p", { class: "dim", text: `nano Agent ${ME.version} · ${t("model_label")}: ${ME.model || "-"}` }), h("p", null, h("button", { onclick: async () => { await post("/logout"); showLogin(); }, text: t("logout") }))));
}

// ---------- boot ----------
async function boot() {
  wireHeaderActions();
  const s = await (await fetch("/api/strings")).json(); S = s.strings; lang = s.lang; S._liff = s.liff_id || ""; document.documentElement.lang = lang;
  const hp = new URLSearchParams(location.hash.slice(1));   // #token=...&tab=mind&sub=skills ; a fragment never reaches server logs
  if (hp.get("token")) {
    history.replaceState(null, "", location.pathname);
    await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token: hp.get("token") }) });
  }
  let r = await fetch("/api/me", { credentials: "same-origin" });
  if (r.status === 401 && await liffLogin()) r = await fetch("/api/me", { credentials: "same-origin" });
  if (r.status === 401) return showLogin();
  ME = await r.json(); applyUi(ME.prefs || {}); await loadMascots().catch(() => {}); startMascotClock(); routeFromHash(hp); addEventListener("resize", () => drawTabs()); drawTabs(); render(); pollPill();
}
setInterval(pollPill, 5000);
setInterval(() => { if (tab === "home") refreshHome(); }, 15000);
boot();
})();
