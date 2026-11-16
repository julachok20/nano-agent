"""The console page: one static HTML shell plus gateway/static/console.js. The shell holds no private data; everything
private comes from the owner-only /api routes after login. All text in the page is set with textContent (never innerHTML),
because tool results, web pages and chat text are untrusted."""
from __future__ import annotations

from .. import __version__

CSS = """
:root{
  --bg:#0b0f19;--bg-elev:#101726;--panel:#131b2e;--panel-2:#182238;--line:#23304a;
  --txt:#eef2fb;--dim:#8fa0be;--accent:#ff7a2a;--accent-2:#38bdf8;--accent-ink:#ffffff;
  --ok:#34d399;--warn:#fbbf24;--bad:#fb7185;--gap:16px;--radius:18px;--radius-sm:12px;
  --shadow:0 12px 32px rgba(4,8,18,.34);--font-sans:system-ui,-apple-system,"Segoe UI","Noto Sans Thai",Tahoma,sans-serif;
  --font-mono:ui-monospace,SFMono-Regular,Consolas,monospace;
}
html[data-accent=cyan]{--accent:#38d6ff;--accent-ink:#04131c}
html[data-accent=violet]{--accent:#a78bfa;--accent-ink:#110a24}
html[data-accent=green]{--accent:#34d399;--accent-ink:#041c13}
html[data-accent=orange]{--accent:#ff7a2a;--accent-ink:#ffffff}
html[data-accent=rose]{--accent:#fb7185;--accent-ink:#ffffff}
html[data-accent=blue]{--accent:#60a5fa;--accent-ink:#071426}
html[data-density=compact]{--gap:10px}html[data-density=roomy]{--gap:22px}
html[data-size=s]{font-size:14px}html[data-size=m]{font-size:16px}html[data-size=l]{font-size:18px}html[data-size=xl]{font-size:20px}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:16px/1.5 var(--font-sans);min-height:100vh}
button,input,textarea,select{font:inherit}
button{cursor:pointer}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

PREPAINT = (
    '<script>(function(){try{var t=localStorage.getItem("nano.theme"),a=localStorage.getItem("nano.accent");'
    'if(t)document.documentElement.dataset.theme=t;if(a)document.documentElement.dataset.accent=a;}catch(e){}})();</script>'
)


def page() -> str:
    return f"""<!doctype html><html lang="en" data-theme="dark" data-accent="orange" data-density="normal" data-size="m"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="robots" content="noindex">
<title>nano Agent</title><link rel="icon" href="/static/favicon.png">{PREPAINT}<style>{CSS}</style><link rel="stylesheet" href="/static/dashboard.css?v={__version__}"></head><body>
<header>
  <div class="brand-left">
    <b class="brand-name">nanoAgent</b>
    <span class="open-pill">Open Source</span>
    <span id="pill" class="pill"><i></i><span id="pilltxt"></span></span>
  </div>
  <div class="brand-right">
    <button id="theme-quick" class="icon-btn" type="button" aria-label="Toggle Light or Dark appearance"></button>
    <span class="brand-mark" title="nano Agent"><img src="/static/logo-icon.png" alt="n"></span>
  </div>
</header>
<main id="view"></main><nav id="tabs"></nav><script src="/static/console.js?v={__version__}"></script></body></html>"""
