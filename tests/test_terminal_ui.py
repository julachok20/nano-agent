"""Terminal setup should remain usable at ordinary terminal sizes."""

import os
import re
from io import StringIO

import pytest

from nanoagent import wizard


class FakeTTY(StringIO):
    def isatty(self):
        return True


def test_setup_uses_alternate_screen_and_restores_it_on_error(monkeypatch):
    output = FakeTTY()
    monkeypatch.setattr(wizard.sys, "stdin", FakeTTY())
    monkeypatch.setattr(wizard.sys, "stdout", output)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("NO_COLOR", raising=False)

    with pytest.raises(RuntimeError):
        with wizard.setup_screen():
            raise RuntimeError("setup failed")

    assert output.getvalue().startswith("\x1b[?1049h")
    assert output.getvalue().endswith("\x1b[?1049l")


def test_setup_menu_can_reach_last_provider_on_24_line_terminal(monkeypatch):
    monkeypatch.setattr(wizard.shutil, "get_terminal_size", lambda _: os.terminal_size((80, 24)))
    ui = wizard.TerminalUI()
    ui._tty = True
    frames = []
    ui._frame = lambda title, body, footer="": frames.append((body, footer))
    keys = iter(["\x1b[B"] * 11 + ["\r"])
    ui._read_key = lambda: next(keys)
    options = [(str(i), f"Provider {i}") for i in range(12)]

    assert ui.choose("Choose a provider", options, "0") == "11"
    assert all(len(body) <= 8 for body, _ in frames)
    assert any("7-12/12" in footer for _, footer in frames)


def test_setup_frame_fits_24_line_terminal(monkeypatch, capsys):
    monkeypatch.setattr(wizard.shutil, "get_terminal_size", lambda _: os.terminal_size((80, 24)))
    ui = wizard.TerminalUI()
    ui._tty = True
    ui.section = "Finish"
    ui._frame("Review your setup", ["Name: Alex", "Model: fake / fake-1",
                                    "Console access: local", "LINE: Not connected",
                                    "Your API key is hidden.", "Save these settings?"])

    plain = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", capsys.readouterr().out).splitlines()
    assert len(plain) <= 24
    assert max(map(len, plain)) <= 80
    assert any("Review your setup" in line for line in plain)
