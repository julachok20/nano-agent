"""The console page: one static HTML shell plus gateway/static/console.js. The shell holds no private data; everything
private comes from the owner-only /api routes after login. All text in the page is set with textContent (never innerHTML),
because tool results, web pages and chat text are untrusted."""
from __future__ import annotations

from .. import __version__

CSS = """
:root{
  --bg:#f8f7fc;--bg-elev:#ffffff;--panel:rgba(255,255,255,.84);--panel-2:#f0edfa;--line:rgba(30,36,56,.10);
  --txt:#172033;--dim:#65718a;--accent:#ff7200;--accent-2:#38bdf8;--accent-ink:#ffffff;
  --ok:#34d399;--warn:#fbbf24;--bad:#fb7185;--gap:18px;--radius:22px;--radius-sm:14px;
  --shadow:0 16px 40px rgba(48,38,76,.08);--font-sans:system-ui,-apple-system,"Segoe UI","Noto Sans Thai",Tahoma,sans-serif;
  --font-mono:ui-monospace,SFMono-Regular,Consolas,monospace;
}
html[data-accent=cyan]{--accent:#38d6ff;--accent-ink:#04131c}
html[data-accent=violet]{--accent:#a78bfa;--accent-ink:#110a24}
html[data-accent=green]{--accent:#34d399;--accent-ink:#041c13}
html[data-accent=orange]{--accent:#ff6a1a;--accent-ink:#ffffff}
html[data-accent=rose]{--accent:#fb7185;--accent-ink:#ffffff}
html[data-accent=blue]{--accent:#60a5fa;--accent-ink:#071426}
html[data-density=compact]{--gap:12px}html[data-density=roomy]{--gap:24px}
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
    return f"""<!doctype html><html lang="en" data-theme="light" data-accent="orange" data-density="normal" data-size="m"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="robots" content="noindex">
<title>nano Agent</title><link rel="icon" href="/static/favicon.png">{PREPAINT}<style>{CSS}</style><link rel="stylesheet" href="/static/dashboard.css?v={__version__}"></head><body>
<header>
  <div class="brand-left">
    <a class="brand-lockup" href="/console" aria-label="nano Agent home"><span class="logo-wrap"><img class="logo logo-light-img" src="/static/logo-light-theme.png" alt="nano Agent"><img class="logo logo-dark-img" src="/static/logo-dark-theme.png" alt=""></span></a>
    <span id="pill" class="pill"><i></i><span id="pilltxt"></span></span>
  </div>
  <div class="brand-right">
    <button id="hdr-search" class="icon-btn" type="button" aria-label="Quick chat"></button>
    <button id="hdr-notif" class="icon-btn" type="button" aria-label="Approvals"></button>
    <button id="theme-quick" class="icon-btn" type="button" aria-label="Toggle Light or Dark appearance"></button>
    <span class="brand-mark" title="nano Agent"><img src="/static/mascot-n.png" alt="n"></span>
  </div>
</header>
<main id="view"></main><nav id="tabs"></nav><script src="/static/console.js?v={__version__}"></script></body></html>"""

