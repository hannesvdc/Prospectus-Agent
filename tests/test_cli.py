"""Tests for the unified CLI contract (dispatch only — subcommands are stubbed)."""
from __future__ import annotations

import os

import pytest

from prospectus_agent import cli


def _isolate_env(monkeypatch, **overrides):
    """Give the test its own os.environ copy (auto-restored) with DEFAULT_PROFILE
    removed by default, so cli.main doesn't apply a real profile mid-test."""
    env = {k: v for k, v in os.environ.items() if k != "DEFAULT_PROFILE"}
    env.update(overrides)
    monkeypatch.setattr(os, "environ", env)


def test_no_args_runs_daily(monkeypatch):
    _isolate_env(monkeypatch)
    calls = []
    monkeypatch.setattr("prospectus_agent.daily_run.main", lambda: calls.append("daily") or 0)
    monkeypatch.setattr("prospectus_agent.refine.main", lambda: calls.append("refine") or 0)
    assert cli.main([]) == 0
    assert calls == ["daily"]


def test_refine_flag_runs_refine(monkeypatch):
    _isolate_env(monkeypatch)
    calls = []
    monkeypatch.setattr("prospectus_agent.daily_run.main", lambda: calls.append("daily") or 0)
    monkeypatch.setattr("prospectus_agent.refine.main", lambda: calls.append("refine") or 0)
    assert cli.main(["--refine"]) == 0
    assert calls == ["refine"]


def test_sent_flag_runs_mark_sent(monkeypatch):
    _isolate_env(monkeypatch)
    calls = []
    monkeypatch.setattr("prospectus_agent.daily_run.main", lambda: calls.append("daily") or 0)
    monkeypatch.setattr("prospectus_agent.mark_sent.main", lambda: calls.append("sent") or 0)
    assert cli.main(["--sent"]) == 0
    assert calls == ["sent"]


def _stub_followup(monkeypatch, calls):
    monkeypatch.setattr(
        "prospectus_agent.followup_run.main",
        lambda refine=False, mark_sent=False: calls.append(("followup", refine, mark_sent)) or 0,
    )


def test_followup_flag_runs_followup(monkeypatch):
    _isolate_env(monkeypatch)
    calls = []
    _stub_followup(monkeypatch, calls)
    assert cli.main(["--followup"]) == 0
    assert calls == [("followup", False, False)]


def test_followup_refine_stacks(monkeypatch):
    _isolate_env(monkeypatch)
    calls = []
    _stub_followup(monkeypatch, calls)
    monkeypatch.setattr("prospectus_agent.refine.main", lambda: calls.append("initial-refine") or 0)
    # --followup --refine => follow-up scope, refine action (NOT the initial refine).
    assert cli.main(["--followup", "--refine"]) == 0
    assert calls == [("followup", True, False)]


def test_followup_sent_stacks(monkeypatch):
    _isolate_env(monkeypatch)
    calls = []
    _stub_followup(monkeypatch, calls)
    monkeypatch.setattr("prospectus_agent.mark_sent.main", lambda: calls.append("initial-sent") or 0)
    # --followup --sent => follow-up scope, mark-sent action (NOT the initial mark_sent).
    assert cli.main(["--followup", "--sent"]) == 0
    assert calls == [("followup", False, True)]


def test_refine_and_sent_are_rejected(monkeypatch):
    _isolate_env(monkeypatch)
    with pytest.raises(SystemExit):
        cli.main(["--refine", "--sent"])
    with pytest.raises(SystemExit):
        cli.main(["--followup", "--refine", "--sent"])


def test_runall_dispatches_and_forwards_flags(monkeypatch):
    _isolate_env(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "prospectus_agent.run_all.main",
        lambda followup=False, refine=False, sent=False, deliver=False, live=False:
            calls.append((followup, refine, sent, deliver, live)) or 0,
    )
    assert cli.main(["--runall"]) == 0
    assert cli.main(["--runall", "--refine"]) == 0
    assert cli.main(["--runall", "--followup", "--sent"]) == 0
    assert cli.main(["--runall", "--deliver", "--live"]) == 0
    assert calls == [
        (False, False, False, False, False),
        (False, True, False, False, False),
        (True, False, True, False, False),
        (False, False, False, True, True),
    ]


def test_runall_rejects_profile(monkeypatch):
    _isolate_env(monkeypatch)
    with pytest.raises(SystemExit):
        cli.main(["--runall", "--profile", "x"])


def test_exit_code_is_propagated(monkeypatch):
    _isolate_env(monkeypatch)
    monkeypatch.setattr("prospectus_agent.daily_run.main", lambda: 3)
    assert cli.main([]) == 3


def test_version_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "prospectus-agent" in capsys.readouterr().out


def test_profile_flag_wires_paths(monkeypatch, tmp_path):
    from prospectus_agent import paths
    _isolate_env(monkeypatch)
    monkeypatch.setattr(paths, "HOME", tmp_path)
    (tmp_path / "profile.acme.yaml").write_text("company: {}\n")
    monkeypatch.setattr("prospectus_agent.daily_run.main", lambda: 0)

    assert cli.main(["--profile", "acme"]) == 0
    # config derives the per-business paths from this single env var.
    assert os.environ["PROSPECTUS_PROFILE"] == "acme"


def test_default_profile_env_is_honored(monkeypatch, tmp_path):
    from prospectus_agent import paths
    _isolate_env(monkeypatch, DEFAULT_PROFILE="acme")
    monkeypatch.setattr(paths, "HOME", tmp_path)
    (tmp_path / "profile.acme.yaml").write_text("company: {}\n")
    monkeypatch.setattr("prospectus_agent.daily_run.main", lambda: 0)

    assert cli.main([]) == 0  # no --profile, falls back to $DEFAULT_PROFILE
    assert os.environ["PROSPECTUS_PROFILE"] == "acme"


def test_profile_flag_missing_file_errors(monkeypatch, tmp_path):
    from prospectus_agent import paths
    _isolate_env(monkeypatch)
    monkeypatch.setattr(paths, "HOME", tmp_path)
    with pytest.raises(SystemExit):
        cli.main(["--profile", "doesnotexist"])


def test_profile_flag_rejects_bad_name(monkeypatch):
    _isolate_env(monkeypatch)
    with pytest.raises(SystemExit):
        cli.main(["--profile", "../etc/passwd"])


def test_deliver_no_profile_fans_out_all_profiles(monkeypatch):
    _isolate_env(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "prospectus_agent.run_all.main",
        lambda followup=False, refine=False, sent=False, deliver=False, live=False:
            calls.append((followup, deliver, live)) or 0,
    )
    # No --profile => deliver fans out to every profile (each handles both scopes).
    assert cli.main(["--deliver", "--live"]) == 0
    assert cli.main(["--deliver"]) == 0
    assert cli.main(["--deliver", "--followup", "--live"]) == 0
    assert calls == [
        (False, True, True),     # --deliver --live: both scopes, all profiles, send
        (False, True, False),    # --deliver: both scopes, all profiles, dry-run
        (True, True, True),      # --deliver --followup --live: follow-ups only, all, send
    ]


def _make_profile(monkeypatch, tmp_path, name="acme"):
    from prospectus_agent import paths
    monkeypatch.setattr(paths, "HOME", tmp_path)
    (tmp_path / f"profile.{name}.yaml").write_text("company: {}\n")


def test_deliver_with_profile_runs_both_scopes(monkeypatch, tmp_path):
    _isolate_env(monkeypatch)
    _make_profile(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        "prospectus_agent.deliver_run.main",
        lambda followup=False, live=False: calls.append((followup, live)) or 0,
    )
    # One profile, plain --deliver => initials THEN follow-ups.
    assert cli.main(["--profile", "acme", "--deliver", "--live"]) == 0
    assert calls == [(False, True), (True, True)]


def test_deliver_profile_followup_runs_followups_only(monkeypatch, tmp_path):
    _isolate_env(monkeypatch)
    _make_profile(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        "prospectus_agent.deliver_run.main",
        lambda followup=False, live=False: calls.append((followup, live)) or 0,
    )
    assert cli.main(["--profile", "acme", "--deliver", "--followup"]) == 0
    assert calls == [(True, False)]


def test_deliver_rejects_conflicting_actions(monkeypatch):
    _isolate_env(monkeypatch)
    with pytest.raises(SystemExit):
        cli.main(["--deliver", "--refine"])
    with pytest.raises(SystemExit):
        cli.main(["--deliver", "--sent"])


def test_live_requires_deliver(monkeypatch):
    _isolate_env(monkeypatch)
    with pytest.raises(SystemExit):
        cli.main(["--live"])
