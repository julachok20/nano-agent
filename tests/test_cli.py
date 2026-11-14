"""The CLI and the setup wizard (interactive with scripted answers, and non-interactive), doctor, models, i18n completeness."""
from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest

from nano_agent import __version__, cli, config, i18n, keystore, paths, wizard
from nano_agent.providers import base as pbase

SRC = Path(__file__).parents[1] / "src" / "nano_agent"
FAKE_KEY = "sk-" + "Zx9Cv8Bn7Mk6" * 3   # scan:allow


def main(*argv) -> int:
    return cli.main(list(argv))


def setup_fake(*extra):
    return main("setup", "--non-interactive", "--provider", "fake", "--model", "fake-1", "--skip-test", "--name", "Alex", "--timezone", "UTC", *extra)


def test_version_and_help(capsys):
    with pytest.raises(SystemExit) as e:
        main("--version")
    assert e.value.code == 0 and f"nano-agent {__version__}" in capsys.readouterr().out
    assert main() == 0 and "setup" in capsys.readouterr().out


def test_non_interactive_setup_with_fake_provider_then_doctor(capsys):
    assert setup_fake() == 0
    cfg = config.load()
    assert cfg["models"]["chat"] == "fake/fake-1" and cfg["general"]["owner_name"] == "Alex" and cfg["gateway"]["exposure"] == "local" and cfg["gateway"]["host"] == "127.0.0.1"
    assert keystore.get("owner.token") and len(keystore.get("owner.token")) >= 32
    capsys.readouterr()
    assert main("doctor", "--offline") == 0
    out = capsys.readouterr().out
    assert "✓" in out and "✗" not in out and "Everything needed is in place" in out
    assert main("doctor", "--offline", "--json") == 0
    data = json.loads(capsys.readouterr().out)
    assert data["version"] == __version__ and all(c["level"] != "fail" for c in data["checks"])


def test_api_key_comes_from_env_never_from_argv_and_never_lands_in_config(monkeypatch, capsys):
    monkeypatch.setenv("MY_TEST_KEY", FAKE_KEY)
    assert main("setup", "--non-interactive", "--provider", "openai", "--model", "gpt-x", "--api-key-env", "MY_TEST_KEY", "--skip-test") == 0
    assert keystore.get("provider.openai") == FAKE_KEY
    assert FAKE_KEY not in paths.config_path().read_text()
    capsys.readouterr()
    main("config", "show")
    assert FAKE_KEY not in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main("setup", "--non-interactive", "--provider", "openai", "--model", "m", "--api-key", FAKE_KEY)   # no such flag, on purpose


def test_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("NOPE_KEY", raising=False)
    with pytest.raises(SystemExit) as e:
        main("setup", "--non-interactive", "--provider", "openai", "--model", "m", "--api-key-env", "NOPE_KEY")
    assert "NOPE_KEY" in str(e.value)
    with pytest.raises(SystemExit) as e:
        main("setup", "--non-interactive", "--provider", "openai", "--model", "m")
    assert "needs an API key" in str(e.value)
    with pytest.raises(SystemExit):
        main("setup", "--non-interactive", "--provider", "bogus", "--model", "m")


def test_line_and_exposure_flags(monkeypatch):
    monkeypatch.setenv("LS", "secret-for-test")   # scan:allow
    monkeypatch.setenv("LT", "token-for-test")   # scan:allow
    assert setup_fake("--line-secret-env", "LS", "--line-token-env", "LT", "--liff-id", "1234567890-AbCdEfGh", "--exposure", "cloudflare", "--public-url", "https://bot.example.org") == 0   # scan:allow
    cfg = config.load()
    assert cfg["line"]["enabled"] and cfg["line"]["liff_id"] == "1234567890-AbCdEfGh" and cfg["gateway"]["exposure"] == "cloudflare" and cfg["gateway"]["public_url"] == "https://bot.example.org"   # scan:allow
    assert keystore.get("line.channel_secret") == "secret-for-test" and "secret-for-test" not in paths.config_path().read_text()


class Script:
    """Scripted answers for the interactive wizard."""

    def __init__(self, answers, secrets_):
        self.a, self.s, self.out = list(answers), list(secrets_), []

    def prompter(self):
        return wizard.Prompter(input_fn=lambda q: (self.out.append(q), self.a.pop(0))[1], secret_fn=lambda q: (self.out.append(q), self.s.pop(0))[1], out=self.out.append)


def test_interactive_wizard_english_end_to_end(home, monkeypatch):
    monkeypatch.setattr(wizard.shutil, "which", lambda _: None)   # pretend Docker is absent
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    #   language, name, tz, provider(openai=1), model, fast, exposure(local=1), home, line(later=1), google, voice
    s = Script(["1", "Sam", "Asia/Bangkok", "1", "gpt-x", "gpt-y", "1", str(home), "1", "n", "y"], [FAKE_KEY])
    a = wizard.collect(s.prompter())
    assert a["language"] == "en" and a["owner_name"] == "Sam" and a["provider"] == "openai" and a["api_key"] == FAKE_KEY and a["chat_model"] == "gpt-x" and a["line_later"] is True
    wizard.apply(a)
    cfg = config.load()
    assert cfg["models"] == {"chat": "openai/gpt-x", "fast": "openai/gpt-y", "vision": ""} and cfg["general"]["timezone"] == "Asia/Bangkok" and not cfg["line"]["enabled"]
    text = "\n".join(map(str, s.out))
    assert FAKE_KEY not in text and "Tailscale" in text and "Cloudflare" in text and "Local only" in text and "(hidden)" in text


def test_interactive_wizard_thai_and_line_now(home, monkeypatch):
    monkeypatch.setattr(wizard.shutil, "which", lambda _: "/usr/bin/docker")
    s = Script(["2", "สม", "Asia/Bangkok", "12", "", "", "1", str(home), "2", "", "y", "y", "n"], ["line-secret-x", "line-token-x"])   # 12 = fake provider; line now; sandbox no
    a = wizard.collect(s.prompter())
    out = "\n".join(map(str, s.out))
    assert a["language"] == "th" and "ตั้งค่า" in out and a["provider"] == "fake" and a["line"]["channel_secret"] == "line-secret-x" and a["sandbox"] is False
    assert "https://developers.line.biz/console/" in out
    wizard.apply(a)
    assert config.load()["general"]["language"] == "th" and keystore.get("line.channel_token") == "line-token-x"


def test_wizard_ctrl_c_saves_nothing(home):
    def boom(q):
        raise KeyboardInterrupt
    rc = wizard.run_interactive(wizard.Prompter(input_fn=boom, out=lambda *_: None))
    assert rc == 130 and not paths.config_path().exists()


def test_exposure_hints_are_commands_not_actions():
    assert any("tailscale serve" in x for x in wizard.exposure_hint("tailscale", 8099))
    assert any("cloudflared tunnel" in x for x in wizard.exposure_hint("cloudflare", 8099))
    assert any("reverse_proxy" in x for x in wizard.exposure_hint("domain", 8099)) and wizard.exposure_hint("local", 8099) == []


def test_models_test_checks_key_and_model_and_never_prints_the_key(monkeypatch, capsys):
    monkeypatch.setenv("K", FAKE_KEY)
    main("setup", "--non-interactive", "--provider", "openai", "--model", "gpt-x", "--api-key-env", "K", "--skip-test")
    capsys.readouterr()
    pbase.DEFAULT_TRANSPORT = httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}))
    try:
        assert main("models", "test") == 0 and "✓ chat: openai/gpt-x" in capsys.readouterr().out
        pbase.DEFAULT_TRANSPORT = httpx.MockTransport(lambda r: httpx.Response(401, text="bad key " + FAKE_KEY))
        assert main("models", "test", "--all") == 1
        out = capsys.readouterr().out
        assert "✗ chat" in out and "rejected the API key" in out and FAKE_KEY not in out
        pbase.DEFAULT_TRANSPORT = httpx.MockTransport(lambda r: httpx.Response(404, json={}))
        assert main("models", "test") == 1 and "model name or the base URL" in capsys.readouterr().out
    finally:
        pbase.DEFAULT_TRANSPORT = None


def test_models_add_set_key_use_list(monkeypatch, capsys):
    setup_fake()
    monkeypatch.setenv("GK", FAKE_KEY)
    assert main("models", "add", "groq", "--api-key-env", "GK", "--model", "llama-x", "--role", "fast") == 0
    assert main("models", "use", "chat", "groq/llama-y") == 0
    assert main("models", "set-key", "nope") == 2
    capsys.readouterr()
    assert main("models", "list") == 0
    out = capsys.readouterr().out
    assert "groq" in out and "model fast: groq/llama-x" in out and "model chat: groq/llama-y" in out and FAKE_KEY not in out and "…" in out
    assert main("models", "use", "chat", "no-slash") == 2


def test_status_when_stopped_and_stop_when_not_running(capsys):
    setup_fake()
    capsys.readouterr()
    assert main("status", "--json") == 3
    info = json.loads(capsys.readouterr().out)
    assert info["running"] is False and info["console"].startswith("http://127.0.0.1:8099")
    assert main("stop") == 0 and main("logs") == 1


def test_token_command_prints_fragment_url(capsys):
    setup_fake()
    capsys.readouterr()
    assert main("token") == 0
    out = capsys.readouterr().out
    assert "#token=" + keystore.get("owner.token") in out and "secret token" in out


def test_skills_cli_stages_then_enables_after_ack(tmp_path, capsys):
    setup_fake()
    f = tmp_path / "s.md"
    f.write_text("---\nname: cli-skill\ndescription: from the cli\n---\nDo the thing.\n", encoding="utf-8")
    assert main("skills", "add", str(f)) == 0 and "staged: cli-skill" in capsys.readouterr().out
    assert main("skills", "enable", "cli-skill", "--yes") == 0
    main("skills", "list")
    assert "cli-skill: from the cli" in capsys.readouterr().out


def test_line_helpers(capsys):
    setup_fake()
    assert main("line", "pair") == 1   # LINE not set up yet
    assert main("line", "guide") == 0 and "developers.line.biz" in capsys.readouterr().out
    cfg = config.load()
    cfg["line"]["enabled"] = True
    config.save(cfg)
    assert main("line", "pair") == 0 and re.search(r"pair [0-9a-f]{6}", capsys.readouterr().out)
    assert main("line", "status") == 0


def test_config_set_and_types():
    setup_fake()
    assert main("config", "set", "gateway.port", "8123") == 0 and config.load()["gateway"]["port"] == 8123
    assert main("config", "set", "sandbox.enabled", "true") == 0 and config.load()["sandbox"]["enabled"] is True


def test_uninstall_keeps_data_unless_purged():
    setup_fake()
    assert main("uninstall") == 0 and paths.config_path().exists()
    assert main("uninstall", "--purge", "--yes") == 0 and not paths.home().exists()


def test_doctor_fails_clearly_without_setup(capsys):
    import shutil
    shutil.rmtree(paths.home())
    assert main("doctor", "--offline") == 1
    assert "nano-agent setup" in capsys.readouterr().out


def test_config_toml_roundtrip_with_special_characters():
    cfg = config.load()
    cfg["general"]["owner_name"] = 'Zoë "Z" \\ Ng'
    cfg["providers"]["a.b"] = {"kind": "openai", "base_url": "http://x/v1", "key_ref": "provider.a.b"}
    config.save(cfg)
    back = config.load()
    assert back["general"]["owner_name"] == 'Zoë "Z" \\ Ng' and back["providers"]["a.b"]["base_url"] == "http://x/v1"


def test_chat_command_one_shot(capsys):
    setup_fake()
    capsys.readouterr()
    assert main("chat", "hello", "world") == 0 and "[fake] hello world" in capsys.readouterr().out


# ---------------------------------------------------------------- i18n completeness

def test_english_and_thai_have_the_same_keys_and_no_blank_values():
    en, th = i18n._load("en"), i18n._load("th")
    assert i18n.missing_keys() == {"th": []} and set(th) == set(en)
    assert all(v.strip() for v in list(en.values()) + list(th.values()))
    for k, v in en.items():   # same placeholders in both languages
        assert sorted(re.findall(r"\{(\w+)\}", v)) == sorted(re.findall(r"\{(\w+)\}", th[k])), k


def test_every_key_used_in_code_exists():
    en = i18n._load("en")
    used = set()
    for p in SRC.rglob("*.py"):
        used |= set(re.findall(r"""\bt\(\s*["']([a-z_]+\.[a-z_.0-9]+)["']""", p.read_text(encoding="utf-8")))
    used |= {f"doctor.{c}" for c in ("python", "home", "config", "secrets_file", "provider_key", "provider_ping", "database", "tools", "i18n", "port", "line", "line_paired", "exposure", "sandbox", "google", "opt_psutil", "opt_keyring")}
    assert not [k for k in used if k not in en], [k for k in used if k not in en]
    js = (SRC / "gateway/static/console.js").read_text(encoding="utf-8")
    ui_used = {k for k in re.findall(r"""\bt\(\s*["']([a-z_0-9]+)["']""", js) if not k.endswith("_")} | {"level_assistant", "level_buddy", "level_friend"} | {f"tab_{x}" for x in ("home", "chat", "manage", "mind", "work", "settings")}
    assert not [k for k in ui_used if f"ui.{k}" not in en], [k for k in ui_used if f"ui.{k}" not in en]


def test_thai_text_is_thai_and_english_has_no_thai():
    en, th = i18n._load("en"), i18n._load("th")
    thai = re.compile("[฀-๿]")
    assert not [k for k, v in en.items() if thai.search(v) and k != "setup.lang_q"]   # the language question is deliberately bilingual
    assert sum(1 for k, v in th.items() if k.startswith("ui.") and thai.search(v)) > 100
    assert i18n.t("ui.tab_home", "th") == "หน้าหลัก" and i18n.t("no.such.key", "th") == "no.such.key"
