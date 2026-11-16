// nano Agent console. Vanilla JS, no build step. SECURITY: all dynamic text is set with textContent only (no HTML string APIs).
(() => {
"use strict";
const $ = (s, el = document) => el.querySelector(s);
let S = {}, ME = {}, lang = "en", tab = "home", sub = {}, chatRole = "chat";
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
  arrow: [["path", { d: "M5 12h14M13 6l6 6-6 6" }]]
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
const clear = () => { view().replaceChildren(); return view(); };
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
  ["chat", "chat", "tab_chat"],
  ["manage", "manage", "tab_manage"],
  ["computer", "system", "sub_system"],
  ["automation", "auto", "sub_auto"],
  ["skills", "skills", "sub_skills"],
  ["settings", "settings", "tab_settings"]
];
const HUB_OF = { activity: "home", memory: "settings", learning: "settings", know: "settings", mind: "settings", work: "computer" };
function drawTabs() {
  $("#tabs").replaceChildren(
    h("div", { class: "nav-brand" }, h("img", { src: "/static/logo-icon.png", alt: "" }), h("span", { text: "nanoAgent" })),
    ...HUBS.map(([k, ic, lb]) =>
      h("button", { class: (HUB_OF[tab] || tab) === k ? "on" : "", onclick: () => go(k) },
        h("span", { class: "nav-ico" }, ico(ic)),
        h("span", { class: "nav-lbl", text: k === "automation" && innerWidth < 960 ? (lang === "th" ? "ออโต้" : "Auto") : t(lb) }))));
}
function go(k) { tab = k; drawTabs(); render(); }
function render() { ({ home: vHome, chat: vChat, manage: vManage, computer: vWork, automation: vWork, skills: vMind,
  settings: vSettings, activity: vWork, memory: vMind, learning: vMind, know: vMind, mind: vMind, work: vWork })[tab](); }

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
const setOrb = s => { orbState = s; const o = $("#orb"); if (o) o.dataset.state = s; };
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
function assistantMascot() {
  return h("span", { class: "assistant-mascot", "aria-hidden": "true" },
    h("img", { class: "assistant-logo", src: "/static/mascot-n.png", alt: "" }),
    h("span", { class: "assistant-working" }, h("i"), h("i"), h("i")));
}
async function vHome() {
  const v = clear();
  const date = new Date(), hour = date.getHours();
  const greeting = lang === "th" ? (hour < 11 ? "สวัสดีตอนเช้า" : hour < 17 ? "สวัสดีตอนบ่าย" : "สวัสดีตอนเย็น")
    : (hour < 11 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening");
  const askInp = h("input", { placeholder: lang === "th" ? "ถามอะไรก็ได้..." : "Ask anything...", "aria-label": t("chat_placeholder") });
  const submitQuick = () => {
    const q = askInp.value.trim();
    if (q) startChatWith(q);
    else go("chat");
  };
  askInp.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); submitQuick(); } });

  const subline = lang === "th"
    ? h("p", { class: "jv-subline" }, "ผู้ช่วย AI ส่วนตัวแบบโอเพ่นซอร์ส พร้อม ", h("b", { text: "พูด ฟัง และลงมือทำ" }), " เพื่อคุณ")
    : h("p", { class: "jv-subline" }, "Your open-source personal AI assistant. I can ", h("b", { text: "speak, listen, and act" }), " for you.");

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
            waveBars(5),
            h("button", { id: "orb", class: "jv-orb", "data-state": "idle", onclick: orbTap, "aria-label": t("orb_tap") },
              assistantMascot(),
              h("strong", { text: lang === "th" ? "แตะเพื่อพูด" : "Tap to speak" }),
              h("small", null, h("i"), h("span", { text: lang === "th" ? "พร้อมรับฟัง" : "Listening ready" }))),
            waveBars(5))),
        h("div", { id: "heard", class: "jv-heard" }),
        h("div", { id: "said", class: "jv-said" }),
        h("div", { class: "quick-ask" },
          ico("sparkle"),
          askInp,
          h("button", { class: "pri", onclick: submitQuick, "aria-label": t("send") }, ico("arrow")))),
      h("div", { id: "home-approval-panel", class: "jv-slot", style: "grid-area:appr" }),
      h("div", { id: "home-activity-panel", class: "jv-slot", style: "grid-area:bg" }),
      h("div", { class: "jv-bottom" },
        h("div", { id: "home-project-panel", class: "jv-slot" }),
        h("div", { id: "home-news-panel", class: "jv-slot" }))));
  refreshHome();
}
async function refreshHome() {
  if (tab !== "home") return;
  const [st, dr, tk, ac] = await Promise.all([api("/state"), api("/drafts"), api("/tasks"), api("/activity")]);
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
        : jvEmpty("manage", lang === "th" ? "ไม่มีงานค้าง" : "All caught up")))));
  $("#home-memory-panel").replaceChildren(jvPanel("mem", "memory", t("memory_title"), "memory", null,
    jvMemoryGraph(factCount),
    h("div", { class: "jv-pct" }, h("strong", { text: `${factCount} memories` }), h("small", { text: t("memory_counts", { f: st.memory.fact || 0, r: st.memory.rule || 0 }) }))));
  $("#home-approval-panel").replaceChildren(jvPanel("appr", "approval", t("drafts_title", { n: dr.drafts.length }), "manage", "drafts",
    dr.drafts.length
      ? dr.drafts.slice(0, 3).map(d => h("div", { class: "jv-row" }, h("span", { class: "jv-dot" }), h("span", { class: "jv-name", text: d.channel + " → " + d.target }), h("em", { text: "Review" })))
      : jvEmpty("approval", t("drafts_none"))));
  const recent = [...ac.running, ...ac.done.slice(0, 3)];
  $("#home-activity-panel").replaceChildren(jvPanel("bg", "activity", t("work_title"), "activity", null,
    recent.length ? recent.map(a => h("div", { class: "jv-activity-row" }, h("span", { class: "jv-dot " + (a.status === "running" ? "running" : "") }),
      h("span", { text: a.title }), h("small", { text: a.status === "running" ? Math.round(a.secs) + "s" : a.status }))) : jvEmpty("activity", t("work_idle"))));
  $("#home-project-panel").replaceChildren(jvPanel("", "projects", lang === "th" ? "โปรเจกต์" : "Projects", "computer", null,
    jvEmpty("projects", lang === "th" ? "ยังไม่มีโปรเจกต์ที่ติดตาม" : "No projects tracked yet")));
  $("#home-news-panel").replaceChildren(jvPanel("", "news", lang === "th" ? "ข่าวสาร" : "News", "automation", null,
    jvEmpty("news", lang === "th" ? "ยังไม่ได้เชื่อมต่อฟีดข่าว" : "No news feed connected")));
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
async function vChat() {
  const v = clear(); const box = h("div", { id: "chatbox", class: "chat-messages", role: "log", "aria-live": "polite" });
  const inp = h("textarea", { placeholder: t("chat_placeholder"), rows: 2, "aria-label": t("chat_placeholder") });
  if (sub.chatDraft) { inp.value = sub.chatDraft; delete sub.chatDraft; }
  const h1 = await api("/history?session=console");
  const starters = lang === "th"
    ? ["ช่วยวางแผนงานวันนี้", "สรุปสิ่งที่ต้องทำ", "ช่วยร่างข้อความสั้นๆ"]
    : ["Plan my day", "Summarize my open tasks", "Help me draft a message"];
  if (!h1.messages.length) {
    box.append(h("div", { class: "chat-empty" }, h("img", { src: "/static/logo-icon.png", alt: "" }),
      h("h2", { text: lang === "th" ? "คุยกับ Nano Agent" : "Talk to Nano Agent" }),
      h("p", { text: lang === "th" ? "ถาม วางแผน หรือให้ช่วยจัดการงานของคุณ" : "Ask a question, plan your day, or work through a task." }),
      h("div", { class: "jv-quick-prompts" },
        ...starters.map(s => h("button", { onclick: () => { inp.value = s; inp.focus(); }, text: s })))));
  }
  h1.messages.forEach(m => box.append(h("div", { class: "msg " + m.role, text: m.text })));
  const choices = modelChoices();
  if (!choices.some(([r]) => r === chatRole)) chatRole = choices[0][0];
  const activeModel = () => (choices.find(([r]) => r === chatRole) || choices[0])[1];
  const subLabel = h("small", { text: activeModel() });
  const modelSelect = h("select", {
    class: "model-select",
    "aria-label": t("model_label"),
    onchange: e => { chatRole = e.target.value; subLabel.textContent = activeModel(); }
  }, choices.map(([role, name, label]) => h("option", { value: role, selected: role === chatRole ? "" : null, text: `${label}: ${name}` })));
  const send = async () => {
    const text = inp.value.trim(); if (!text) return; inp.value = ""; box.querySelector(".chat-empty")?.remove(); box.append(h("div", { class: "msg user", text }));
    const wait = h("div", { class: "msg note", text: t("chat_thinking") }); box.append(wait);
    try { const r = await ask(text, "console", chatRole); wait.remove(); box.append(h("div", { class: "msg assistant", text: r.text }));
      if (r.tools && r.tools.length) box.append(h("div", { class: "msg note", text: t("chat_used") + r.tools.map(x => x.name).join(", ") }));
      if (r.new_drafts && r.new_drafts.length) box.append(draftsPanel(r.new_drafts, () => go("chat")));
    } catch (e) { wait.remove(); }
    box.scrollTop = box.scrollHeight;
  };
  inp.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
  v.append(viewHeading(t("tab_chat"), lang === "th" ? "พื้นที่คุยกับผู้ช่วยของคุณ" : "Your direct space with Nano Agent", 2),
    h("section", { class: "chat-stage" },
      h("div", { class: "chat-stage-head", "data-agent-id": "nano-agent" },
        h("div", { class: "chat-agent-identity", "data-agent-role": "primary" },
          h("div", { class: "chat-avatar" }, h("img", { src: "/static/mascot-n.png", alt: "" })),
          h("div", { class: "chat-head-info" }, h("strong", { text: "Nano Agent" }), subLabel)),
        h("div", { class: "chat-head-controls" }, modelSelect, h("span", { class: "chat-online", title: "Ready" }))),
      box,
      h("div", { class: "chat-composer" }, inp, h("div", { class: "chat-composer-bottom" },
        h("small", { text: lang === "th" ? "Enter เพื่อส่ง · Shift+Enter ขึ้นบรรทัดใหม่" : "Enter to send · Shift+Enter for a new line" }),
        h("button", { class: "pri", onclick: send, text: t("send") + " →" })))));
  box.scrollTop = box.scrollHeight;
}

// ---------- manage ----------
async function vManage() {
  const v = clear(); const cur = sub.manage || "tasks";
  v.append(viewHeading(t("tab_manage"), lang === "th" ? "งานและรายการรออนุมัติ" : "Tasks and approvals in one place", 3),
    chips([["tasks", t("sub_tasks")], ["drafts", t("sub_drafts")]], cur, k => { sub.manage = k; vManage(); }));
  if (cur === "drafts") { const d = await api("/drafts"); v.append(d.drafts.length ? draftsPanel(d.drafts, vManage) : panel(t("drafts_none"))); return; }
  const d = await api("/tasks"); const title = h("input", { placeholder: t("task_title") }), due = h("input", { placeholder: t("task_due") });
  v.append(panel(t("task_add"), title, h("div", { style: "height:6px" }), due, h("p", null, h("button", { class: "pri", onclick: async () => { const r = await act("/tasks", { title: title.value, due: due.value }); if (r.ok) vManage(); }, text: t("add") }))));
  v.append(panel(t("tasks_title"), ...d.tasks.map(x => h("div", { class: "row" }, h("span", { class: "grow", style: x.done ? "text-decoration:line-through;opacity:.5" : "", text: x.title }), h("span", { class: "dim", text: x.due }),
    x.done ? null : h("button", { onclick: async () => { await post("/tasks/" + x.id + "/complete"); vManage(); }, text: t("done") })))));
  const rt = h("input", { placeholder: t("rem_text") }), rw = h("input", { placeholder: t("rem_when") });
  v.append(panel(t("reminders_title"), ...d.reminders.map(r => h("div", { class: "row" }, h("span", { class: "grow", text: r.text }), h("span", { class: "dim", text: r.due }))), rt, h("div", { style: "height:6px" }), rw,
    h("p", null, h("button", { onclick: async () => { const r = await act("/reminders", { text: rt.value, when: rw.value }); if (r.ok) vManage(); }, text: t("add") }))));
}

// ---------- mind: memory, skills, learning ----------
async function vMind() {
  const v = clear(); const fixed = ["skills", "memory", "learning", "know"].includes(tab) ? tab : null;
  const cur = fixed || sub.mind || "memory";
  v.append(viewHeading(t("sub_" + cur), lang === "th" ? "ความจำ ทักษะ และการเรียนรู้" : "Memory, skills, and learning", cur === "skills" ? 6 : 7));
  if (!fixed) v.append(chips([["memory", t("sub_memory")], ["skills", t("sub_skills")], ["learning", t("sub_learning")], ["know", t("sub_know")]], cur, k => { sub.mind = k; vMind(); }));
  ({ memory: mMemory, skills: mSkills, learning: mLearning, know: mKnow })[cur](v);
}
async function mMemory(v) {
  const d = await api("/memory"); const inp = h("input", { placeholder: t("memory_add_ph") });
  v.append(panel(t("memory_add"), inp, h("p", null, h("button", { class: "pri", onclick: async () => { const r = await act("/memory", { text: inp.value }); if (r.ok) vMind(); }, text: t("add") }))));
  v.append(panel(t("memory_title"), d.items.length ? d.items.map(m => h("div", { class: "row" }, h("span", { class: "tag", text: m.kind }), h("span", { class: "grow", text: m.text }), h("span", { class: "dim", text: m.source }),
    h("button", { class: "bad", onclick: async () => { await del("/memory/" + m.id); vMind(); }, text: t("delete") }))) : h("p", { class: "dim", text: t("memory_none") })));
}
async function mSkills(v) {
  const d = await api("/skills"); const txt = h("textarea", { placeholder: t("skill_import_ph") }), url = h("input", { placeholder: "https://github.com/owner/repo" });
  v.append(panel(t("skills_title"), d.skills.length ? d.skills.map(s => h("div", { class: "row" }, h("span", { class: "grow" }, h("b", { text: s.name }), h("div", { class: "dim", text: s.description })),
    h("span", { class: "tag " + (s.pending ? "warn" : s.enabled ? "ok" : ""), text: s.pending ? t("skill_pending") : s.enabled ? t("on") : t("off") }), h("button", { onclick: () => skillSheet(s), text: t("open") }))) : h("p", { class: "dim", text: t("skills_none") })));
  v.append(panel(t("skill_import"), h("p", { class: "dim", text: t("skill_import_note") }), url, h("p", null, h("button", { onclick: async () => { const r = await post("/skills/import", { kind: "url", url: url.value }); toast(JSON.stringify((r.results || []).map(x => x.ok ? x.name : x.error))); vMind(); }, text: t("import_github") })),
    txt, h("p", null, h("button", { onclick: async () => { const r = await post("/skills/import", { kind: "text", text: txt.value }); toast(JSON.stringify((r.results || []).map(x => x.ok ? x.name : x.error))); vMind(); }, text: t("import_text") }))));
}
async function skillSheet(s) {
  const r = await api("/skills/" + encodeURIComponent(s.name)); const v = clear(); const ta = h("textarea", { style: "min-height:260px" }); ta.value = r.text || "";
  const ack = h("input", { type: "checkbox", style: "width:auto" });
  v.append(panel(s.name, r.review ? h("div", null, h("span", { class: "tag " + (r.review.verdict === "ok" ? "ok" : "bad"), text: r.review.verdict }), h("pre", { text: r.review.findings.join("\n") || t("review_clean") }),
      h("label", null, ack, " " + t("review_ack"))) : null, ta,
    h("p", null, !r.pending ? h("button", { class: "pri", onclick: async () => { const b = ta.value.split(/^---\s*$/m); await api("/skills/" + encodeURIComponent(s.name), { method: "PUT", body: { body: (b[2] || ta.value).trim() } }); toast(t("saved")); }, text: t("save") }) : null,
      h("button", { onclick: async () => { const x = await post("/skills/" + encodeURIComponent(s.name) + "/toggle", { enabled: r.pending ? true : !s.enabled, ack: ack.checked }); if (x.ok === false) toast(x.error); else { sub.mind = "skills"; vMind(); } }, text: r.pending ? t("skill_enable") : (s.enabled ? t("skill_disable") : t("skill_enable")) }),
      h("button", { class: "bad", onclick: async () => { await del("/skills/" + encodeURIComponent(s.name)); vMind(); }, text: t("delete") }), h("button", { onclick: vMind, text: t("back") }))));
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
  const v = clear(); const fixed = ({ computer: "system", automation: "auto", activity: "activity" })[tab];
  const cur = fixed || sub.work || "activity";
  v.append(viewHeading(t("sub_" + cur), lang === "th" ? "กิจกรรม ระบบอัตโนมัติ และสถานะ" : "Activity, automations, and system status", 5));
  if (!fixed) v.append(chips([["activity", t("sub_activity")], ["auto", t("sub_auto")], ["system", t("sub_system")]], cur, k => { sub.work = k; vWork(); }));
  if (cur === "activity") { const a = await api("/activity"); const row = x => h("div", { class: "row" }, h("span", { class: "tag " + (x.status === "done" ? "ok" : x.status === "failed" ? "bad" : "warn"), text: x.status }), h("span", { class: "grow" }, h("b", { text: x.title }), x.steps.length ? h("div", { class: "dim", text: x.steps.slice(-3).map(s => s.text).join(" · ") }) : null), h("span", { class: "dim", text: Math.round(x.secs) + "s" }));
    v.append(panel(t("running_title"), a.running.length ? a.running.map(row) : h("p", { class: "dim", text: t("work_idle") })), panel(t("recent_title"), a.done.map(row))); }
  if (cur === "auto") { const a = await api("/automations"); const nm = h("input", { placeholder: t("auto_name") }), pr = h("textarea", { placeholder: t("auto_prompt") }), sc = h("input", { placeholder: '{"daily": "08:00"}' });
    v.append(panel(t("auto_title"), a.items.map(x => h("div", { class: "row" }, h("span", { class: "grow" }, h("b", { text: x.name }), h("div", { class: "dim", text: JSON.stringify(x.schedule) + (x.last_status ? " · " + x.last_status : "") })),
      h("button", { onclick: async () => { await post("/automations/" + x.id + "/toggle", { enabled: !x.enabled }); vWork(); }, text: x.enabled ? t("pause") : t("resume") }), h("button", { onclick: async () => { const r = await post("/automations/" + x.id + "/run"); toast(r.status || r.error); }, text: t("run_now") }),
      x.builtin ? null : h("button", { class: "bad", onclick: async () => { await del("/automations/" + x.id); vWork(); }, text: t("delete") })))),
      panel(t("auto_new"), nm, pr, sc, h("p", null, h("button", { class: "pri", onclick: async () => { let s; try { s = JSON.parse(sc.value); } catch (e) { return toast("JSON"); } const r = await act("/automations", { name: nm.value, prompt: pr.value, schedule: s }); if (r.ok) vWork(); }, text: t("add") })))); }
  if (cur === "system") { const s = await api("/system"), i = s.info; const bar = (l, p) => p == null ? null : h("div", { class: "row" }, h("span", { class: "grow", text: l }), h("div", { class: "bar", style: "width:50%" }, h("i", { style: "width:" + p + "%" })), h("span", { class: "dim", text: p + "%" }));
    v.append(panel(t("system_title"), h("p", { class: "dim", text: `${i.host} · ${i.os} · Python ${i.python} · nano Agent ${i.version}` }), bar("CPU", i.cpu_pct), bar("RAM", i.ram_pct), bar("Disk", i.disk_pct),
      i.gpu ? bar("GPU " + i.gpu.name, i.gpu.util_pct) : null, i.cpu_pct == null ? h("p", { class: "dim", text: t("system_psutil") }) : null),
      panel(t("health_title"), s.health.map(c => h("div", { class: "row" }, h("span", { class: "tag " + (c.ok ? "ok" : "bad"), text: c.ok ? "OK" : "!" }), h("span", { class: "grow", text: c.name }), h("span", { class: "dim", text: c.detail })))),
      panel(t("providers_title"), Object.entries(s.providers).map(([n, p]) => h("div", { class: "row" }, h("b", { text: n }), h("span", { class: "dim grow", text: p.kind + " · " + p.base_url }))), h("p", null, h("button", { onclick: async () => { const r = await post("/models/test"); toast(r.ok ? "OK: " + r.model : r.message); }, text: t("test_model") }))),
      panel(t("tools_title"), h("p", { class: "dim", text: s.tools.join(", ") }))); }
}

// ---------- settings ----------
const ACCENT_HEX = { orange: "#ff6a00", blue: "#38bdf8", violet: "#a78bfa", green: "#34d399", cyan: "#38d6ff", rose: "#fb7185" };
async function vSettings() {
  const v = clear(); const name = h("input", { value: ME.owner_name || "" }), tz = h("input", { value: ME.timezone || "" });
  const lg = h("select", null, ["en", "th"].map(l => h("option", { value: l, selected: l === lang ? "" : null, text: l === "en" ? "English" : "ไทย" })));
  const baseTheme = currentBaseTheme();
  const themes = [
    ["light", lang === "th" ? "สว่าง (Light)" : "Light", lang === "th" ? "พื้นหลังสว่าง สะอาดตา เหมาะกับกลางวัน" : "Clean luminous workspace for daytime focus"],
    ["dark", lang === "th" ? "มืด (Dark)" : "Dark", lang === "th" ? "พื้นหลังเข้ม สบายตาในที่แสงน้อย" : "Deep slate workspace for low-light comfort"]
  ];
  const curAccent = document.documentElement.dataset.accent || "orange";
  v.append(viewHeading(t("tab_settings"), lang === "th" ? "ปรับหน้าตาและข้อมูลของคุณ" : "Make Nano Agent feel like yours", 6),
    h("div", { class: "settings-shortcuts" },
      h("button", { onclick: () => go("memory"), text: t("sub_memory") }),
      h("button", { onclick: () => go("learning"), text: t("sub_learning") }),
      h("button", { onclick: () => go("know"), text: t("sub_know") })),
    panel(lang === "th" ? "รูปแบบหน้าจอ" : "Appearance",
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
        })))));
  v.append(panel(t("settings_title"), field(t("set_name"), name), field(t("set_tz"), tz), field(t("set_lang"), lg),
    h("p", null, h("button", { class: "pri", onclick: async () => { const r = await act("/settings", { owner_name: name.value, timezone: tz.value, language: lg.value }); if (r.ok) { toast(t("saved")); boot(); } }, text: t("save") }))));
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
  ME = await r.json(); applyUi(ME.prefs || {}); if (HUBS.some(h => h[0] === hp.get("tab"))) { tab = hp.get("tab"); if (hp.get("sub")) sub[tab] = hp.get("sub"); } drawTabs(); render(); pollPill();
}
setInterval(pollPill, 5000);
setInterval(() => { if (tab === "home") refreshHome(); }, 15000);
boot();
})();
