"""Tests for the unified CLI contract (dispatch only — subcommands are stubbed)."""
from __future__ import annotations

import pytest

from prospectus_agent import cli


def test_no_args_runs_daily(monkeypatch):
    calls = []
    monkeypatch.setattr("prospectus_agent.daily_run.main", lambda: calls.append("daily") or 0)
    monkeypatch.setattr("prospectus_agent.refine.main", lambda: calls.append("refine") or 0)
    assert cli.main([]) == 0
    assert calls == ["daily"]


def test_refine_flag_runs_refine(monkeypatch):
    calls = []
    monkeypatch.setattr("prospectus_agent.daily_run.main", lambda: calls.append("daily") or 0)
    monkeypatch.setattr("prospectus_agent.refine.main", lambda: calls.append("refine") or 0)
    assert cli.main(["--refine"]) == 0
    assert calls == ["refine"]


def test_exit_code_is_propagated(monkeypatch):
    monkeypatch.setattr("prospectus_agent.daily_run.main", lambda: 3)
    assert cli.main([]) == 3


def test_version_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "prospectus-agent" in capsys.readouterr().out
