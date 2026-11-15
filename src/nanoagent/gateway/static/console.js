// nano Agent console. Vanilla JS, no build step. SECURITY: all dynamic text is set with textContent only (no HTML string APIs).
(() => {
"use strict";
const $ = (s, el = document) => el.querySelector(s);
let S = {}, ME = {}, lang = "en", tab = "home", sub = {};
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
function panel(title, ...kids) { return h("div", { class: "panel" }, title ? h("h3", { text: title }) : null, ...kids); }
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

// ---------- shell ----------
const HUBS = [["home", "⌂", "tab_home"], ["chat", "✎", "tab_chat"], ["manage", "☑", "tab_manage"],
  ["computer", "▣", "sub_system"], ["automation", "◷", "sub_auto"], ["skills", "✦", "sub_skills"], ["settings", "⚙", "tab_settings"]];
const HUB_OF = { activity: "home", memory: "settings", learning: "settings", know: "settings", mind: "settings", work: "computer" };
function drawTabs() { $("#tabs").replaceChildren(...HUBS.map(([k, ic, lb]) => h("button", { class: (HUB_OF[tab] || tab) === k ? "on" : "", onclick: () => go(k) },
  h("span", { text: ic }), k === "automation" && innerWidth < 1001 ? (lang === "th" ? "ออโต้" : "Auto") : t(lb)))); }
function go(k) { tab = k; drawTabs(); render(); }
function render() { ({ home: vHome, chat: vChat, manage: vManage, computer: vWork, automation: vWork, skills: vMind,
  settings: vSettings, activity: vWork, memory: vMind, learning: vMind, know: vMind, mind: vMind, work: vWork })[tab](); }
function applyUi(p) { const r = document.documentElement; if (p["ui.accent"]) r.dataset.accent = p["ui.accent"];
  if (p["ui.theme"]) r.dataset.theme = ({ spark: "dark", black: "modern" })[p["ui.theme"]] || p["ui.theme"];
  if (p["ui.density"]) r.dataset.density = p["ui.density"]; if (p["ui.text_size"]) r.dataset.size = p["ui.text_size"]; }
function viewHeading(title, detail, number) {
  return h("div", { class: "view-heading" }, h("div", null, h("small", { text: `NANO AGENT / ${String(number).padStart(2, "0")}` }), h("h1", { text: title }), h("p", { text: detail })));
}
async function pollPill() {
  try { const r = await api("/activity?count=1"); const n = r.running || 0; const p = $("#pill"); p.classList.toggle("busy", n > 0);
    $("#pilltxt").textContent = n > 0 ? t("pill_busy", { n }) : t("pill_idle"); } catch (e) { /* login screen */ }
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
async function ask(text, session) {
  const r = await post("/chat", { text, session }); return r;
}
function listen() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { toast(t("voice_unsupported")); return; }
  rec = new SR(); rec.lang = lang === "th" ? "th-TH" : "en-US"; rec.interimResults = false;
  setOrb("listening");
  rec.onresult = async e => { const said = e.results[0][0].transcript; setOrb("thinking"); $("#heard").textContent = said;
    try { const r = await ask(said, "voice"); $("#said").textContent = r.text || ""; await speak(r.text || ""); refreshHome(); } catch (x) { setOrb("idle"); } };
  rec.onerror = () => setOrb("idle"); rec.onend = () => { if (orbState === "listening") setOrb("idle"); };
  rec.start();
}
async function orbTap() {
  if (orbState === "listening" && rec) { rec.stop(); return; }
  if (orbState !== "idle") return;
  if (!openerSpoken) { openerSpoken = true; const o = await api("/companion/opener"); $("#said").textContent = o.text; await speak(o.text); return; }
  listen();
}
function sv(tag, props = {}, ...kids) {
  const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(props)) e.setAttribute(k, String(v));
  for (const c of kids.flat()) if (c) e.append(c);
  return e;
}
function dialPoint(r, deg) { const a = deg * Math.PI / 180; return [200 + r * Math.sin(a), 200 - r * Math.cos(a)]; }
function nanoDial(tasks = []) {
  const svg = sv("svg", { class: "jv-dial", viewBox: "-34 -34 468 468", "aria-hidden": "true" });
  for (let i = 0; i < 60; i++) {
    const big = i % 5 === 0, [x1, y1] = dialPoint(big ? 174 : 179, i * 6), [x2, y2] = dialPoint(188, i * 6);
    svg.append(sv("line", { x1, y1, x2, y2, stroke: "var(--accent)", "stroke-opacity": big ? .9 : .35, "stroke-width": big ? 2.2 : 1 }));
  }
  svg.append(sv("circle", { cx: 200, cy: 200, r: 168, fill: "none", stroke: "var(--accent)", "stroke-opacity": .2, "stroke-width": 2 }),
    sv("circle", { class: "jv-spin", cx: 200, cy: 200, r: 118, fill: "none", stroke: "var(--accent)", "stroke-opacity": .4, "stroke-dasharray": "2 7" }),
    sv("circle", { cx: 200, cy: 200, r: 100, fill: "none", stroke: "var(--accent)", "stroke-opacity": .45 }));
  for (const [label, deg] of [["06", 0], ["09", 90], ["12", 180], ["15", 270]]) {
    const [x, y] = dialPoint(210, deg), txt = sv("text", { x, y: y + 5, fill: "#8bb0c4", "font-size": 15, "text-anchor": "middle" });
    txt.textContent = label; svg.append(txt);
  }
  const now = new Date(), hour = now.getHours() + now.getMinutes() / 60;
  if (hour >= 6 && hour <= 18) {
    const deg = (hour - 6) * 30, [x1, y1] = dialPoint(100, deg), [x2, y2] = dialPoint(160, deg);
    svg.append(sv("line", { x1, y1, x2, y2, stroke: "#fff", "stroke-width": 2 }), sv("circle", { cx: x2, cy: y2, r: 6, fill: "#fff" }));
  }
  const today = now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2, "0") + "-" + String(now.getDate()).padStart(2, "0");
  for (const task of tasks.filter(x => !x.done && x.due && x.due.startsWith(today)).slice(0, 4)) {
    const m = /\b(\d{1,2}):(\d{2})\b/.exec(task.due);
    if (!m) continue;
    const dueHour = Number(m[1]) + Number(m[2]) / 60;
    if (dueHour < 6 || dueHour > 18) continue;
    const [x, y] = dialPoint(150, (dueHour - 6) * 30);
    svg.append(sv("circle", { cx: x, cy: y, r: 9, fill: "#fbbf24" }));
  }
  svg.append(sv("circle", { cx: 200, cy: 200, r: 92, fill: "none", stroke: "var(--ok)", "stroke-width": 3 }),
    sv("circle", { cx: 200, cy: 200, r: 86, fill: "var(--panel)", stroke: "var(--ok)", "stroke-width": 2 }));
  const clip = sv("clipPath", { id: "nano-dial-clip" }, sv("circle", { cx: 200, cy: 200, r: 82 }));
  svg.append(sv("defs", {}, clip), sv("image", { href: "/static/logo-icon.png", x: 118, y: 118, width: 164, height: 164, "clip-path": "url(#nano-dial-clip)", preserveAspectRatio: "xMidYMid meet" }));
  return svg;
}
function jvPanel(area, title, number, ...kids) {
  return h("section", { class: "jv-panel", style: `grid-area:${area}` },
    h("h3", null, h("span", { text: title }), h("i", { text: number })), ...kids);
}
function jvEmpty(message) { return h("p", { class: "jv-note", text: message }); }
function jvGo(label, target, section) { return h("button", { class: "jv-link", onclick: () => { if (section) sub[target] = section; go(target); }, text: label }); }
function jvMemoryGraph(count) {
  const svg = sv("svg", { class: "jv-memory-graph", viewBox: "0 0 300 150", "aria-hidden": "true" });
  const points = [[40, 30], [92, 12], [150, 28], [232, 40], [262, 98], [200, 128], [110, 132], [34, 96], [200, 74]];
  points.slice(0, Math.min(count, points.length)).forEach(([x, y], i) => {
    svg.append(sv("line", { x1: 150, y1: 78, x2: x, y2: y, stroke: "var(--accent)", "stroke-opacity": .35 }),
      sv("circle", { cx: x, cy: y, r: 6, fill: ["var(--accent)", "var(--accent)", "var(--warn)", "var(--ok)"][i % 4] }));
  });
  const center = sv("text", { x: 150, y: 84, "text-anchor": "middle", fill: "#e6f5fc", "font-size": 15 }); center.textContent = String(count);
  svg.append(sv("circle", { cx: 150, cy: 78, r: 20, fill: "#0c1f2c", stroke: "#e6f5fc", "stroke-width": 2 }), center);
  return svg;
}
async function vHome() {
  const v = clear();
  const date = new Date(), hour = date.getHours();
  const greeting = lang === "th" ? (hour < 11 ? "สวัสดีตอนเช้า" : hour < 17 ? "สวัสดีตอนบ่าย" : "สวัสดีตอนเย็น")
    : (hour < 11 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening");
  v.append(h("div", { class: "jv-head" },
    h("div", null, h("small", { text: date.toLocaleDateString(lang === "th" ? "th-TH" : undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" }) }),
      h("strong", { text: greeting })), h("div", { id: "home-clock", class: "jv-clock" })),
    h("div", { class: "jv-grid" },
      h("div", { id: "home-chat-panel", class: "jv-slot", style: "grid-area:chat" }),
      h("div", { id: "home-task-panel", class: "jv-slot", style: "grid-area:task" }),
      h("div", { id: "home-news-panel", class: "jv-slot", style: "grid-area:news" }),
      h("div", { class: "jv-core", style: "grid-area:core" }, h("button", { id: "orb", class: "jv-orb", "data-state": "idle", onclick: orbTap, "aria-label": t("orb_tap") }, nanoDial())),
      h("div", { class: "jv-welcome", style: "grid-area:wel" }, h("h2", { text: lang === "th" ? "ยินดีต้อนรับกลับมา" : "Welcome back" }),
        h("p", { id: "home-welcome-note", text: lang === "th" ? "แตะวงกลมเพื่อคุยกับ Nano Agent" : "Tap the circle to talk to Nano Agent" }),
        h("div", { class: "jv-wave", "aria-hidden": "true" }, ...Array.from({ length: 33 }, (_, i) => h("i", { style: `--i:${i};--h:${Math.round(10 + 40 * Math.abs(Math.sin(i * .55)) * (1 - Math.abs(i - 16) / 22))}px` }))),
        h("div", { id: "heard", class: "jv-heard" }), h("div", { id: "said", class: "jv-said" }), jvGo(t("home_chat"), "chat")),
      h("div", { id: "home-project-panel", class: "jv-slot", style: "grid-area:proj" }),
      h("div", { id: "home-memory-panel", class: "jv-slot", style: "grid-area:mem" }),
      h("div", { id: "home-approval-panel", class: "jv-slot", style: "grid-area:appr" }),
      h("div", { id: "home-activity-panel", class: "jv-slot", style: "grid-area:bg" })));
  refreshHome();
}
async function refreshHome() {
  if (tab !== "home") return;
  const [st, dr, tk, ac, ht] = await Promise.all([api("/state"), api("/drafts"), api("/tasks"), api("/activity"), api("/history?session=console")]);
  if (!$("#home-chat-panel")) return;
  $("#orb").replaceChildren(nanoDial(tk.tasks));
  const factCount = (st.memory.fact || 0) + (st.memory.rule || 0);
  $("#home-clock").textContent = new Date().toLocaleTimeString(lang === "th" ? "th-TH" : undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
  const openTasks = tk.tasks.filter(x => !x.done);
  const totalTasks = tk.tasks.length;
  const rows = items => items.map(([title, detail, pct]) => h("div", { class: "jv-row" }, h("span", { class: "jv-dot" }), h("span", { class: "jv-name", text: title }),
    h("span", { class: "jv-rowbar" }, h("i", { style: `width:${pct}%` })), h("em", { text: detail })));
  const recentChats = ht.messages.filter(m => m.role === "user"), chatBars = Array(24).fill(0), nowSeconds = Date.now() / 1000;
  recentChats.forEach(m => { const hoursAgo = Math.floor((nowSeconds - m.ts) / 3600); if (hoursAgo >= 0 && hoursAgo < 24) chatBars[23 - hoursAgo]++; });
  const maxChats = Math.max(1, ...chatBars);
  $("#home-chat-panel").replaceChildren(jvPanel("chat", t("tab_chat"), "01",
    h("div", { class: "jv-split" }, h("span", { class: "jv-big", text: String(recentChats.length) }),
      h("div", { class: "jv-bars", title: lang === "th" ? "ข้อความล่าสุด 24 ชั่วโมง" : "Messages in the last 24 hours" },
        ...chatBars.map(n => h("b", { style: `height:${Math.max(5, n / maxChats * 100)}%` })))),
    recentChats.length ? recentChats.slice(-3).reverse().map(m => h("div", { class: "jv-chat-row" }, h("span", { text: m.text.slice(0, 52) }), h("small", { text: when(m.ts) })))
      : jvEmpty(lang === "th" ? "ยังไม่มีบทสนทนา" : "No conversations yet"), jvGo(t("home_chat"), "chat")));
  const completed = totalTasks - openTasks.length, pct = totalTasks ? completed / totalTasks : 0;
  $("#home-task-panel").replaceChildren(jvPanel("task", t("sub_tasks"), "02",
    h("div", { class: "jv-ringrow" },
      h("div", { class: "jv-ring", style: `--done:${Math.round(pct * 100)}%` }, h("span", { text: `${completed}/${totalTasks}` })),
      h("div", { class: "jv-task-rows" }, openTasks.length ? rows(openTasks.slice(0, 3).map(x => [x.title, x.due || "", x.priority === 1 ? 30 : x.priority === 2 ? 60 : 90])) : jvEmpty("No urgent tasks"))),
    h("div", { class: "jv-segments" }, ...Array.from({ length: 10 }, (_, i) => h("i", { class: i < Math.round(pct * 10) ? "on" : "" })))));
  $("#home-news-panel").replaceChildren(jvPanel("news", "News", "05", jvEmpty("No news feed connected")));
  $("#home-project-panel").replaceChildren(jvPanel("proj", "Projects", "03", jvEmpty("No projects tracked yet")));
  $("#home-memory-panel").replaceChildren(jvPanel("mem", t("memory_title"), "04", jvMemoryGraph(factCount),
    h("div", { class: "jv-pct" }, h("span", { class: "jv-big", text: String(factCount) }), h("small", { text: t("memory_counts", { f: st.memory.fact || 0, r: st.memory.rule || 0 }) })), jvGo(t("home_review"), "memory")));
  $("#home-approval-panel").replaceChildren(jvPanel("appr", t("drafts_title", { n: dr.drafts.length }), "06",
    dr.drafts.length ? rows(dr.drafts.slice(0, 3).map(d => [d.channel + " → " + d.target, "Review", 60])) : jvEmpty(t("drafts_none")),
    jvGo(t("home_review"), "manage", "drafts")));
  const recent = [...ac.running, ...ac.done.slice(0, 3)];
  $("#home-activity-panel").replaceChildren(jvPanel("bg", t("work_title"), "07",
    recent.length ? recent.map(a => h("div", { class: "jv-activity-row" }, h("span", { class: "jv-dot " + (a.status === "running" ? "running" : "") }),
      h("span", { text: a.title }), h("small", { text: a.status === "running" ? Math.round(a.secs) + "s" : a.status }))) : jvEmpty(t("work_idle")),
    jvGo(t("home_review"), "activity")));
}
function draftsPanel(list, after) {
  return panel(t("drafts_title", { n: list.length }), h("p", { class: "dim", text: t("drafts_note") }), ...list.map(d => h("div", { class: "row" },
    h("span", { class: "tag", text: d.channel + " → " + d.target }), h("div", { class: "grow", text: d.text }),
    h("button", { class: "pri", onclick: async () => { const r = await post("/drafts/" + d.id + "/approve"); toast(r.ok ? t("drafts_sent") : r.error); after(); }, text: t("approve_send") }),
    h("button", { class: "bad", onclick: async () => { await post("/drafts/" + d.id + "/cancel"); after(); }, text: t("cancel") }))));
}

// ---------- chat ----------
async function vChat() {
  const v = clear(); const box = h("div", { id: "chatbox", class: "chat-messages", role: "log", "aria-live": "polite" });
  const inp = h("textarea", { placeholder: t("chat_placeholder"), rows: 2, "aria-label": t("chat_placeholder") });
  const h1 = await api("/history?session=console");
  if (!h1.messages.length) box.append(h("div", { class: "chat-empty" }, h("img", { src: "/static/logo-icon.png", alt: "" }),
    h("h2", { text: lang === "th" ? "คุยกับ Nano Agent" : "Talk to Nano Agent" }),
    h("p", { text: lang === "th" ? "ถาม วางแผน หรือให้ช่วยจัดการงานของคุณ" : "Ask a question, plan your day, or work through a task." })));
  h1.messages.forEach(m => box.append(h("div", { class: "msg " + m.role, text: m.text })));
  const send = async () => {
    const text = inp.value.trim(); if (!text) return; inp.value = ""; box.querySelector(".chat-empty")?.remove(); box.append(h("div", { class: "msg user", text }));
    const wait = h("div", { class: "msg note", text: t("chat_thinking") }); box.append(wait);
    try { const r = await ask(text, "console"); wait.remove(); box.append(h("div", { class: "msg assistant", text: r.text }));
      if (r.tools && r.tools.length) box.append(h("div", { class: "msg note", text: t("chat_used") + r.tools.map(x => x.name).join(", ") }));
      if (r.new_drafts && r.new_drafts.length) box.append(draftsPanel(r.new_drafts, () => go("chat")));
    } catch (e) { wait.remove(); }
    box.scrollTop = box.scrollHeight;
  };
  inp.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
  v.append(viewHeading(t("tab_chat"), lang === "th" ? "พื้นที่คุยกับผู้ช่วยของคุณ" : "Your direct space with Nano Agent", 2),
    h("section", { class: "chat-stage" },
      h("div", { class: "chat-stage-head" }, h("div", { class: "chat-avatar" }, h("img", { src: "/static/logo-icon.png", alt: "" })),
        h("div", null, h("strong", { text: "Nano Agent" }), h("small", { text: ME.model || "AI assistant" })), h("span", { class: "chat-online", text: "●" })),
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
async function vSettings() {
  const v = clear(); const name = h("input", { value: ME.owner_name || "" }), tz = h("input", { value: ME.timezone || "" });
  const lg = h("select", null, ["en", "th"].map(l => h("option", { value: l, selected: l === lang ? "" : null, text: l === "en" ? "English" : "ไทย" })));
  const themes = [
    ["dark", "Dark", lang === "th" ? "จอเข้มแบบ Personal Assistant" : "The Personal Assistant console look"],
    ["modern", "Modern", lang === "th" ? "พื้นดำ ขอบคม สีส้ม Nano" : "Deep black surfaces and Nano orange accents"],
    ["calm", "Calm", lang === "th" ? "โทนสีนุ่ม อ่านสบาย" : "Soft slate and sage for a quieter workspace"],
    ["minimal", "Minimal", lang === "th" ? "เรียบ โปร่ง ใช้งานง่าย" : "Light, open, and simple to use"]
  ];
  v.append(viewHeading(t("tab_settings"), lang === "th" ? "ปรับหน้าตาและข้อมูลของคุณ" : "Make Nano Agent feel like yours", 6),
    h("div", { class: "settings-shortcuts" },
      h("button", { onclick: () => go("memory"), text: t("sub_memory") }),
      h("button", { onclick: () => go("learning"), text: t("sub_learning") }),
      h("button", { onclick: () => go("know"), text: t("sub_know") })),
    panel(lang === "th" ? "รูปแบบหน้าจอ" : "Appearance",
      h("p", { class: "dim", text: lang === "th" ? "เลือกหน้าตาที่ต้องการ เปลี่ยนได้ตลอด" : "Choose a look. You can change it any time." }),
      h("div", { class: "theme-options" }, themes.map(([key, title, detail]) => h("button", {
        class: "theme-option theme-option-" + key + (document.documentElement.dataset.theme === key ? " selected" : ""),
        "aria-pressed": document.documentElement.dataset.theme === key ? "true" : "false",
        onclick: async () => { const r = await post("/learning/pref", { setting: "ui.theme", value: key });
          if (r.ok) { ME.prefs["ui.theme"] = key; applyUi(ME.prefs); vSettings(); } else toast(r.error || "Could not save appearance"); }
      }, h("span", { class: "theme-preview" }, h("i"), h("i"), h("i")), h("strong", { text: title }), h("small", { text: detail }))))));
  v.append(panel(t("settings_title"), field(t("set_name"), name), field(t("set_tz"), tz), field(t("set_lang"), lg),
    h("p", null, h("button", { class: "pri", onclick: async () => { const r = await act("/settings", { owner_name: name.value, timezone: tz.value, language: lg.value }); if (r.ok) { toast(t("saved")); boot(); } }, text: t("save") }))));
  v.append(panel(t("about_title"), h("p", { class: "dim", text: `nano Agent ${ME.version} · ${t("model_label")}: ${ME.model || "-"}` }), h("p", null, h("button", { onclick: async () => { await post("/logout"); showLogin(); }, text: t("logout") }))));
}

// ---------- boot ----------
async function boot() {
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
