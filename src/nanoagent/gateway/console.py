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
"""


def page() -> str:
    return f"""<!doctype html><html lang="en" data-accent="cyan" data-density="normal" data-size="m"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="robots" content="noindex">
<title>nano Agent</title><link rel="icon" href="/static/favicon.png"><style>{CSS}</style></head><body>
<header><img src="/static/logo-icon.png" alt=""><b>nano Agent</b><span class="sp"></span><span id="pill" class="pill"><i></i><span id="pilltxt"></span></span></header>
<main id="view"></main><nav id="tabs"></nav><script src="/static/console.js?v={__version__}"></script></body></html>"""
