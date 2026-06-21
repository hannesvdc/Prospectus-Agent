"""Tests for --runall (fan-out across profiles; subprocess stubbed)."""
from __future__ import annotations

from types import SimpleNamespace

from prospectus_agent import run_all


def test_profile_names_lists_named_profiles_excluding_example(monkeypatch, tmp_path):
    for fname in ("profile.open-numerics.yaml", "profile.reactionstudio.yaml",
                  "profile.example.yaml", "profile.yaml", "notes.txt"):
        (tmp_path / fname).write_text("company: {}\n")
    monkeypatch.setattr(run_all.paths, "HOME", tmp_path)
    assert run_all.profile_names() == ["open-numerics", "reactionstudio"]


def test_main_runs_each_profile(monkeypatch, tmp_path):
    (tmp_path / "profile.a.yaml").write_text("x")
    (tmp_path / "profile.b.yaml").write_text("x")
    monkeypatch.setattr(run_all.paths, "HOME", tmp_path)

    ran = []
    monkeypatch.setattr(
        run_all.subprocess, "run",
        lambda cmd, **k: ran.append(cmd) or SimpleNamespace(returncode=0),
    )
    assert run_all.main() == 0
    profiles = [cmd[cmd.index("--profile") + 1] for cmd in ran]
    assert profiles == ["a", "b"]


def test_main_returns_nonzero_if_any_profile_fails(monkeypatch, tmp_path):
    (tmp_path / "profile.a.yaml").write_text("x")
    (tmp_path / "profile.b.yaml").write_text("x")
    monkeypatch.setattr(run_all.paths, "HOME", tmp_path)
    codes = iter([0, 1])
    monkeypatch.setattr(
        run_all.subprocess, "run",
        lambda cmd, **k: SimpleNamespace(returncode=next(codes)),
    )
    assert run_all.main() == 1


def test_main_no_profiles_is_noop(monkeypatch, tmp_path):
    monkeypatch.setattr(run_all.paths, "HOME", tmp_path)
    assert run_all.main() == 0
