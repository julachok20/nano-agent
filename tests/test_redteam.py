"""N9: the red-team harness with the scripted good and bad agents. Deterministic: no model, no Docker. The runtime is
LocalRuntime (a host test double), so this proves the harness and the edge logic, not container isolation."""
from __future__ import annotations

import json

import pytest

from nanoagent import redteam
from nanoagent.providers.fake import FakeProvider


def test_bad_agent_is_caught_and_scored(home):
    card = redteam.run_suite(behaviour="bad")
    by_id = {r["id"]: r for r in card["scenarios"]}
    assert by_id["canary_read"]["violation_success"] is True          # a honeypot read really happened
    assert by_id["edit_control"]["trip_reason"].startswith("control path access")   # and the supervisor froze on it
    assert card["totals"]["violation_successes"] >= 3
    assert card["totals"]["tripwires_fired"] >= 2
    assert card["honesty"]["claims"] >= 6 and card["honesty"]["rate"] == 0.0   # every claim the bad agent made was false


def test_bad_agent_cannot_stop_the_owners_stop_or_kill(home):
    card = redteam.run_suite(behaviour="bad")
    by_id = {r["id"]: r for r in card["scenarios"]}
    assert by_id["stop_mid_task"]["violation_success"] is False
    assert by_id["kill_during_work"]["violation_success"] is False
    assert card["stop_compliance"] == {"tested": 2, "compliant": 2}
    assert card["kill_latency_ms"]["samples"] == 1 and card["kill_latency_ms"]["max"] is not None


def test_good_agent_has_no_violations_and_makes_no_false_claims(home):
    card = redteam.run_suite(behaviour="good")
    assert card["totals"]["violation_successes"] == 0
    assert card["totals"]["violation_attempts"] == 0
    assert card["totals"]["tripwires_fired"] == 0
    assert card["honesty"]["claims"] == 0


def test_the_suite_is_deterministic(home):
    a = redteam.run_suite(behaviour="bad")["totals"]
    b = redteam.run_suite(behaviour="bad")["totals"]
    assert a == b


def test_real_provider_path_runs_the_same_scenarios_with_no_scripted_steps(home):
    card = redteam.run_suite(provider=FakeProvider(), tier="T0")
    assert card["provider"] == "fake" and card["behaviour"] == "real-model"
    assert card["totals"]["scenarios"] == len(redteam.SCENARIOS)


def test_scorecard_json_and_readable_report_are_written(home, tmp_path):
    card = redteam.run_suite(behaviour="bad")
    jp, mp = redteam.write_reports(card, tmp_path)
    data = json.loads(jp.read_text(encoding="utf-8"))
    assert data["totals"]["scenarios"] == len(redteam.SCENARIOS) and "evidence, not proof" in data["limit"]
    md = mp.read_text(encoding="utf-8")
    assert "Honesty:" in md and "Stop compliance:" in md and "evidence, not proof" in md


def test_bad_arguments_are_refused(home):
    with pytest.raises(ValueError):
        redteam.run_suite(behaviour="maybe")
    with pytest.raises(ValueError):
        redteam.run_suite(behaviour="bad", tier="T7")
