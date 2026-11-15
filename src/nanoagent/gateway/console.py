"""The console page: one static HTML shell plus gateway/static/console.js. The shell holds no private data; everything
private comes from the owner-only /api routes after login. All text in the page is set with textContent (never innerHTML),
because tool results, web pages and chat text are untrusted."""
from __future__ import annotations

from .. import __version__

CSS = """
:root{--bg:#050b14;--panel:#0b1626;--line:#16324a;--txt:#e6f1fa;--dim:#7f9bb3;--accent:#38d6ff;--ok:#34d399;--warn:#fbbf24;--bad:#fb7185;--gap:14px}
html[data-accent=violet]{--accent:#a78bfa}html[data-accent=green]{--accent:#34d399}html[data-accent=orange]{--accent:#fb923c}
html[data-accent=rose]{--accent:#fb7185}html[data-accent=blue]{--accent:#60a5fa}
html[data-density=compact]{--gap:8px}html[data-density=roomy]{--gap:20px}
html[data-size=s]{font-size:14px}html[data-size=m]{font-size:16px}html[data-size=l]{font-size:18px}html[data-size=xl]{font-size:20px}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(1200px 600px at 50% -10%,#0d2540 0,var(--bg) 60%);color:var(--txt);
font:16px/1.45 system-ui,-apple-system,"Segoe UI","Noto Sans Thai",Tahoma,sans-serif;min-height:100vh;padding-bottom:84px}
header{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--line);position:sticky;top:0;background:#050b14ee;z-index:5}
header img{width:30px;height:30px;border-radius:8px}header b{letter-spacing:.04em}header .sp{flex:1}
.pill{border:1px solid var(--line);border-radius:999px;padding:4px 12px;font-size:.8rem;color:var(--dim);background:#0a1a2c;cursor:pointer}
.pill.busy{color:var(--accent);border-color:var(--accent)}.pill i{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--dim);margin-right:6px}
.pill.busy i{background:var(--warn);animation:pulse 1.2s infinite}@keyframes pulse{50%{opacity:.3}}
main{max-width:860px;margin:0 auto;padding:var(--gap)}
main:has(.home-grid){max-width:1370px;padding:24px clamp(16px,3vw,42px)}
.home-intro{display:flex;align-items:end;justify-content:space-between;gap:20px;padding:22px 4px 20px;border-bottom:1px solid var(--line)}
.home-kicker{color:var(--accent);font-size:.72rem;font-weight:800;letter-spacing:.2em;text-transform:uppercase}
.home-intro h1{font-size:clamp(1.8rem,4vw,3.25rem);line-height:1.05;letter-spacing:-.045em;margin:9px 0 10px}
.home-intro p{color:var(--dim);margin:0}.home-chat-button{background:var(--accent);color:#001018;font-weight:800;border:0;padding:11px 20px;white-space:nowrap}
.home-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:18px 0}
.home-metric{background:#0a1828;border:1px solid var(--line);border-radius:12px;padding:12px 16px;display:flex;align-items:baseline;gap:12px}
.home-metric strong{font-size:1.7rem;line-height:1;color:var(--txt);font-variant-numeric:tabular-nums}.home-metric span{color:var(--dim);font-size:.82rem}
.home-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(300px,1.2fr) minmax(0,1fr);gap:14px;align-items:stretch}
.home-stack{display:grid;align-content:start;gap:14px}.home-card,.home-focus{background:linear-gradient(155deg,#10243a,#091521 75%);border:1px solid var(--line);border-radius:16px;padding:20px}
.home-card{min-height:165px}.home-card h2{font-size:.85rem;text-transform:uppercase;letter-spacing:.08em;color:var(--accent);margin:0 0 14px}
.home-card p{margin:8px 0}.home-card-number{font-size:2.5rem;font-weight:800;line-height:1}.home-list-row{display:flex;justify-content:space-between;gap:12px;padding:9px 0;border-top:1px solid var(--line);font-size:.86rem}
.home-list-row span{overflow-wrap:anywhere}.home-list-row small{color:var(--dim);white-space:nowrap}.home-link{border:0;background:none;padding:8px 0 0;color:var(--accent);font-size:.8rem;font-weight:700}
.home-focus{text-align:center;min-height:480px;display:flex;flex-direction:column;align-items:center;justify-content:center;position:relative;overflow:hidden;background:radial-gradient(circle at 50% 44%,#143d53 0,#0c2133 36%,#091521 76%)}
.home-focus:before,.home-focus:after{content:"";position:absolute;border:1px solid #2b526b;border-radius:50%;width:310px;height:310px;top:50%;left:50%;transform:translate(-50%,-45%);opacity:.32;pointer-events:none}
.home-focus:after{width:370px;height:370px;opacity:.15}.home-focus>*{position:relative;z-index:1}.home-clock{font-size:clamp(2.2rem,4vw,3.7rem);font-weight:300;font-variant-numeric:tabular-nums;letter-spacing:-.06em;margin:8px 0 4px}
.home-focus .orb{margin:20px auto 22px}.home-heard{color:var(--dim);font-size:.85rem}.home-said{font-size:.9rem;max-width:32ch}.home-focus p{max-width:34ch;margin:12px auto 0}
@media(max-width:1000px){.home-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.home-focus{grid-column:1/-1;grid-row:1;min-height:390px}.home-stack{grid-row:2}}
@media(max-width:620px){main:has(.home-grid){padding:14px}.home-intro{align-items:start;flex-direction:column;padding:14px 4px}.home-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.home-grid{display:flex;flex-direction:column}.home-focus{order:-1;min-height:310px}.home-focus .orb{width:145px;height:145px;margin:10px auto}.home-focus:before{width:250px;height:250px}.home-focus:after{width:290px;height:290px}.home-stack{display:contents}.home-card{min-height:0}.home-metric{display:block}.home-metric span{display:block;margin-top:6px}}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:var(--gap)}
.chip{border:1px solid var(--line);background:#0a1a2c;color:var(--txt);border-radius:10px;padding:7px 13px;cursor:pointer;font:inherit}
.chip.on{background:var(--accent);color:#001018;border-color:var(--accent);font-weight:600}
.panel{position:relative;background:linear-gradient(180deg,#0c1a2d,#09131f);border:1px solid var(--line);border-radius:12px;padding:var(--gap);margin-bottom:var(--gap)}
.panel:before,.panel:after{content:"";position:absolute;width:14px;height:14px;border:2px solid var(--accent);opacity:.7}
.panel:before{top:-1px;left:-1px;border-right:0;border-bottom:0;border-top-left-radius:12px}
.panel:after{bottom:-1px;right:-1px;border-left:0;border-top:0;border-bottom-right-radius:12px}
.panel h3{margin:0 0 8px;color:var(--accent);font-size:1rem}.dim{color:var(--dim);font-size:.85rem}
.row{display:flex;gap:10px;align-items:center;padding:8px 0;border-top:1px solid #12283d;flex-wrap:wrap}.row:first-of-type{border-top:0}.row .grow{flex:1;min-width:140px}
button,.btn{background:#102338;color:var(--txt);border:1px solid var(--line);border-radius:9px;padding:7px 13px;cursor:pointer;font:inherit}
button.pri{background:var(--accent);color:#001018;border-color:var(--accent);font-weight:600}button.bad{border-color:var(--bad);color:var(--bad)}button:disabled{opacity:.45}
input,textarea,select{background:#07111d;color:var(--txt);border:1px solid var(--line);border-radius:9px;padding:8px 10px;font:inherit;width:100%}
textarea{min-height:90px;resize:vertical}label{display:block;margin:8px 0 3px;color:var(--dim);font-size:.85rem}
nav{position:fixed;bottom:0;left:0;right:0;display:flex;background:#050b14f2;border-top:1px solid var(--line);z-index:6}
nav button{flex:1;border:0;border-radius:0;background:transparent;color:var(--dim);padding:10px 2px;font-size:.78rem}nav button.on{color:var(--accent)}
nav button span{display:block;font-size:1.25rem}
.orb{width:190px;height:190px;border-radius:50%;margin:10px auto;cursor:pointer;background:radial-gradient(circle at 35% 30%,#bff3ff,var(--accent) 38%,#05314a 80%);
box-shadow:0 0 50px color-mix(in srgb,var(--accent) 55%,transparent);transition:transform .2s;display:flex;align-items:center;justify-content:center;color:#001018;font-weight:700}
.orb[data-state=listening]{animation:breath 1.1s infinite;filter:hue-rotate(40deg)}.orb[data-state=thinking]{animation:spin 1.6s linear infinite;opacity:.75}
.orb[data-state=speaking]{animation:breath .7s infinite}@keyframes breath{50%{transform:scale(1.07)}}@keyframes spin{to{filter:hue-rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.orb,.pill i{animation:none!important}}
.msg{padding:9px 12px;border-radius:12px;margin:6px 0;max-width:92%;white-space:pre-wrap;word-break:break-word}
.msg.user{background:#123a57;margin-left:auto}.msg.assistant{background:#0e2236;border:1px solid var(--line)}
.msg.note{background:transparent;color:var(--dim);font-size:.85rem}
pre{background:#050d17;border:1px solid var(--line);border-radius:9px;padding:10px;overflow:auto;font-size:.8rem;white-space:pre-wrap}
.tag{font-size:.72rem;border:1px solid var(--line);border-radius:6px;padding:1px 7px;color:var(--dim)}.tag.ok{color:var(--ok);border-color:var(--ok)}.tag.bad{color:var(--bad);border-color:var(--bad)}.tag.warn{color:var(--warn);border-color:var(--warn)}
.bar{height:8px;border-radius:6px;background:#12283d;overflow:hidden}.bar>i{display:block;height:100%;background:var(--accent)}
.toast{position:fixed;left:50%;transform:translateX(-50%);bottom:96px;background:#0e2236;border:1px solid var(--accent);padding:9px 16px;border-radius:10px;z-index:9;max-width:90vw}
/* Home HUD: compact numbered panels around the companion dial. */
main:has(.home-grid){max-width:1550px;padding:22px clamp(18px,2.6vw,38px)}
.home-intro{padding:10px 0 16px;border:0;align-items:center}.home-intro h1{font-size:clamp(1.45rem,2.4vw,2.15rem);letter-spacing:-.035em;margin:4px 0}.home-intro p{font-size:.88rem}
.home-metrics{margin:4px 0 16px;gap:1px;background:var(--line);border:1px solid var(--line)}
.home-metric{border:0;border-radius:0;background:#091827;padding:11px 18px}.home-metric strong{font-size:1.45rem;color:var(--accent)}
.home-grid{grid-template-columns:minmax(220px,1fr) minmax(390px,1.65fr) minmax(220px,1fr);gap:12px}
.home-stack{gap:12px}.home-card,.home-focus{position:relative;background:#081725;border:1px solid #1c3b4d;border-radius:0;padding:17px 19px}
.home-card:before,.home-card:after,.home-focus:before,.home-focus:after{content:"";position:absolute;width:13px;height:13px;border:0;border-radius:0;background:none;opacity:1;pointer-events:none}
.home-card:before,.home-focus:before{left:-1px;top:-1px;border-left:2px solid var(--accent);border-top:2px solid var(--accent)}
.home-card:after,.home-focus:after{right:-1px;bottom:-1px;border-right:2px solid var(--accent);border-bottom:2px solid var(--accent)}
.home-card{min-height:222px}.home-card-head{display:flex;align-items:center;gap:10px;border-bottom:1px solid #24404f;padding-bottom:10px;margin-bottom:12px}
.home-card-index{color:var(--accent);font:700 .7rem ui-monospace,Consolas,monospace;letter-spacing:.1em}.home-card-head h2{margin:0;flex:1;color:var(--txt);font-size:.75rem;letter-spacing:.16em}.home-card-cross{color:#557c8b}
.home-card p{font-size:.8rem}.home-card .home-link{margin-top:7px;text-transform:uppercase;letter-spacing:.1em}
.home-task-summary{display:flex;align-items:center;gap:17px;margin:4px 0 14px}.home-task-summary>div:last-child{display:grid}.home-task-summary>div:last-child strong{font-size:1.9rem;line-height:1}.home-task-summary small{color:var(--dim);font-size:.7rem;text-transform:uppercase;letter-spacing:.12em}
.home-task-ring{width:77px;height:77px;flex:none;border-radius:50%;background:conic-gradient(var(--accent) var(--done),#1d3b4b 0);display:grid;place-items:center;position:relative}.home-task-ring:after{content:"";position:absolute;inset:8px;border-radius:50%;background:#081725}.home-task-ring strong{z-index:1;font-size:.85rem}
.home-memory-map{height:105px;position:relative;background:radial-gradient(circle,#143646 0,#081725 63%);overflow:hidden}.home-memory-center{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);border:1px solid var(--accent);background:#0a2834;border-radius:50%;width:55px;height:55px;display:grid;place-items:center;font-size:1.25rem;font-weight:700;color:var(--accent);box-shadow:0 0 22px #38d6ff44}.home-memory-node{position:absolute;width:7px;height:7px;border-radius:50%;background:var(--accent);top:calc(50% + 36px * sin(360deg * var(--node) / var(--nodes)));left:calc(50% + 90px * cos(360deg * var(--node) / var(--nodes)));box-shadow:0 0 12px var(--accent)}
.home-focus{min-height:470px;display:flex;flex-direction:column;justify-content:flex-start;text-align:center;overflow:hidden;background:radial-gradient(circle at 50% 52%,#0d3543 0,#091e2c 41%,#081725 76%)}
.home-focus-top{width:100%;display:flex;justify-content:space-between;text-align:left}.home-live{font:.7rem ui-monospace,Consolas,monospace;color:var(--ok);letter-spacing:.12em}
.home-dial{width:min(100%,380px);aspect-ratio:1;margin:8px auto 0;position:relative;display:grid;place-items:center;border-radius:50%;background:radial-gradient(circle,transparent 76%,#254a58 76.5%,transparent 77%,transparent 90%,#254a58 90.5%,transparent 91%)}
.home-dial:before{content:"";position:absolute;inset:20px;border-radius:50%;border:1px solid #2b6474;box-shadow:0 0 30px #38d6ff22,inset 0 0 35px #38d6ff14}.home-dial:after{content:"";position:absolute;inset:35px;border-radius:50%;border:2px solid transparent;border-top-color:var(--accent);border-right-color:#3ab6c8;transform:rotate(-35deg);opacity:.8}
.home-dial-ticks{position:absolute;inset:0}.home-dial-ticks i{position:absolute;left:50%;top:50%;height:7px;width:1px;background:#6fa1aa;transform:rotate(calc(var(--tick)*7.5deg)) translateY(-174px)}
.home-dial-core{position:relative;z-index:1;display:flex;flex-direction:column;align-items:center}.home-clock{font:300 2rem ui-monospace,Consolas,monospace;letter-spacing:.08em;color:#cce6ea;margin:0 0 8px}
.home-focus .orb{width:135px;height:135px;margin:0;border:1px solid #65d8e5;background:radial-gradient(circle at 50% 35%,#164958,#082634 72%);box-shadow:0 0 0 8px #36c7dc16,0 0 44px #38d6ff55;color:var(--txt)}.home-focus .orb img{width:88px;height:88px;object-fit:contain;filter:drop-shadow(0 0 8px #ff934a66)}
.home-dial-action{font-size:.72rem;text-transform:uppercase;letter-spacing:.14em;color:var(--accent);margin-top:12px}.home-welcome{font-size:1.05rem;font-weight:700;letter-spacing:.02em;margin-top:-6px}.home-focus p{margin:6px auto 0;font-size:.78rem}
.home-activity{grid-column:1/-1}.home-activity .home-card{min-height:0}.home-activity-strip{display:flex;gap:18px;min-height:35px}.home-activity-item{display:flex;align-items:center;gap:9px;min-width:0;color:var(--txt);font-size:.83rem}.home-activity-item small{color:var(--dim)}.home-activity-dot{width:7px;height:7px;flex:none;border-radius:50%;background:var(--ok);box-shadow:0 0 10px var(--ok)}.home-activity-dot.idle{background:#557887;box-shadow:none}
@media(min-width:1001px){body{padding-bottom:0}header{margin-left:174px;padding-left:30px}main{margin-left:174px}nav{top:0;right:auto;bottom:0;width:174px;flex-direction:column;align-items:stretch;border-top:0;border-right:1px solid #24404f;padding:76px 12px 16px;background:#071421}nav:before{content:"NANO AGENT";position:absolute;top:20px;left:17px;color:var(--accent);font:700 .76rem ui-monospace,Consolas,monospace;letter-spacing:.18em}nav button{flex:0;text-align:left;padding:12px 9px;display:flex;align-items:center;gap:12px;border-left:2px solid transparent;font-size:.84rem}nav button.on{background:#102a38;border-left-color:var(--accent)}nav button span{font-size:1.1rem;width:23px;text-align:center}}
@media(max-width:1000px){.home-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.home-focus{grid-column:1/-1;grid-row:1}.home-activity{grid-column:1/-1}}
@media(max-width:620px){main:has(.home-grid){padding:12px}.home-intro{padding:8px 0 13px}.home-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.home-grid{display:flex;flex-direction:column}.home-focus{order:-1;min-height:0;padding:15px}.home-dial{width:300px;max-width:100%}.home-dial-ticks i{display:none}.home-focus .orb{width:110px;height:110px}.home-focus .orb img{width:72px;height:72px}.home-stack{display:contents}.home-activity{order:10}.home-card{min-height:0}.home-activity-strip{display:block}}
"""


def page() -> str:
    return f"""<!doctype html><html lang="en" data-accent="cyan" data-density="normal" data-size="m"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="robots" content="noindex">
<title>nano Agent</title><link rel="icon" href="/static/favicon.png"><style>{CSS}</style></head><body>
<header><img src="/static/logo-icon.png" alt=""><b>nano Agent</b><span class="sp"></span><span id="pill" class="pill"><i></i><span id="pilltxt"></span></span></header>
<main id="view"></main><nav id="tabs"></nav><script src="/static/console.js?v={__version__}"></script></body></html>"""
