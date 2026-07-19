"""daily_run resilience + digest behavior.

Guards two things: (1) a failure in one phase must not abort the run, skip the
follow-up sweep, or lose the digest; (2) the follow-up file is written from the
COMPLETE currently-due set, so it appears even when due follow-ups were drafted on
an earlier day (not just this run)."""
from __future__ import annotations

import contextlib

from prospectus_agent import daily_run
from prospectus_agent.schemas import Candidate


def _cand(name, domain):
    return Candidate(name=name, domain=domain, hq_location="", industry="", why_fit="",
                     suggested_applications=[], fit_score=9, source_urls=[])


def _wire(monkeypatch, conn, *, winners, research, followups_fn, generate,
          write_file=None, due=None):
    """Stub every collaborator daily_run.main touches, so the test exercises only its
    own control flow / error handling."""
    @contextlib.contextmanager
    def fake_session(banner):
        yield ("CLIENT", conn)

    monkeypatch.setattr(daily_run.runner, "session", fake_session)
    monkeypatch.setattr(daily_run.db, "max_email_id", lambda c: 0)
    monkeypatch.setattr(daily_run.on_profile, "refresh_profile", lambda client: "PROFILE")
    monkeypatch.setattr(daily_run.discovery, "discover", lambda *a, **k: winners)
    monkeypatch.setattr(daily_run.research, "research_and_draft", research)
    monkeypatch.setattr(daily_run.followups, "run_followups", followups_fn)
    monkeypatch.setattr(daily_run.followups, "due_followup_emails", lambda c: (due or []))
    monkeypatch.setattr(daily_run.outbox, "generate", generate)
    monkeypatch.setattr(daily_run.outbox, "write_file", write_file or (lambda *a, **k: None))
    monkeypatch.setattr(daily_run, "_print_digest", lambda *a, **k: None)


def test_one_company_failing_does_not_abort_run(conn, monkeypatch, capsys):
    drafted, calls = [], {"followups": 0, "generate": 0}

    def research(client, conn, cid, cand, profile):
        if cand.domain == "bad.com":
            raise RuntimeError("boom")
        drafted.append(cand.domain)
        return {"name": cand.name}

    def followups_fn(*a, **k):
        calls["followups"] += 1
        return []

    def generate(conn, **k):
        calls["generate"] += 1
        return None

    _wire(monkeypatch, conn,
          winners=[(1, _cand("Good", "good.com")), (2, _cand("Bad", "bad.com"))],
          research=research, followups_fn=followups_fn, generate=generate)

    rc = daily_run.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert drafted == ["good.com"]         # the good company still drafted
    assert "skipped Bad" in out            # the bad one dropped, not fatal
    assert calls["followups"] == 1         # follow-up sweep still ran
    assert calls["generate"] == 1          # digest still written


def test_followup_failure_still_writes_digest(conn, monkeypatch, capsys):
    calls = {"generate": 0}

    def boom(*a, **k):
        raise RuntimeError("sweep boom")

    def generate(conn, **k):
        calls["generate"] += 1
        return None

    _wire(monkeypatch, conn, winners=[], research=lambda *a, **k: {},
          followups_fn=boom, generate=generate)

    rc = daily_run.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert "follow-up sweep failed" in out
    assert calls["generate"] == 1          # digest written despite the sweep failing


def test_due_followups_written_even_when_none_drafted_this_run(conn, monkeypatch, capsys):
    """The bug: follow-ups drafted on an earlier day never reached followups.md because
    generate() only writes TODAY's new emails. daily_run must render the full due set."""
    captured = {}
    due = [{"id": 1}, {"id": 2}]           # two currently-due follow-ups, drafted earlier

    def write_file(conn, emails, **kwargs):
        captured["emails"] = emails
        captured["basename"] = kwargs.get("basename")
        return ("/out/today", len(emails))

    _wire(monkeypatch, conn, winners=[], research=lambda *a, **k: {},
          followups_fn=lambda *a, **k: [],          # nothing newly drafted this run
          generate=lambda conn, **k: None,          # no TODAY-dated emails
          write_file=write_file, due=due)

    rc = daily_run.main()

    assert rc == 0
    assert captured.get("emails") == due           # followups.md written from the full due set
    assert captured.get("basename") == "followups"
