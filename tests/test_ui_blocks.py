"""Guards for the generative UI renderer (v0.2 addendum, section 6): it is served, loaded by the page,
and never builds HTML from strings. Behaviour is checked in a real browser (see the step-3 build notes)."""
from pathlib import Path

from nanoagent.gateway import console

STATIC = Path(__file__).parents[1] / "src/nanoagent/gateway/static"


def test_renderer_is_served_and_loaded_by_the_page():
    from fastapi.testclient import TestClient

    from nanoagent.gateway.app import create_app
    assert TestClient(create_app()).get("/static/uiblocks.js").status_code == 200
    assert "uiblocks.js" in console.page()


def test_renderer_never_builds_html_from_strings():
    js = (STATIC / "uiblocks.js").read_text(encoding="utf-8")
    for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function", "<iframe"):
        assert bad not in js, f"uiblocks.js uses {bad}"


def test_html_block_is_not_in_the_v02_checker():
    js = (STATIC / "uiblocks.js").read_text(encoding="utf-8")
    checker = js.split("var CHECK = {", 1)[1].split("// Returns", 1)[0]
    assert "html:" not in checker, "html block must not be in the v0.2 checker"
