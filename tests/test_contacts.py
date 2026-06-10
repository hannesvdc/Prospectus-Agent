"""Tests for deterministic email-pattern guessing."""
from __future__ import annotations

import contacts


def test_basic_patterns_and_order():
    out = contacts.guess_emails("Jane Doe", "acme.com")
    assert out == [
        "jane.doe@acme.com",
        "jdoe@acme.com",
        "janedoe@acme.com",
        "jane@acme.com",
    ]


def test_strips_honorifics_and_middle_name():
    out = contacts.guess_emails("Dr. Jane Q. Doe", "acme.com")
    # first=jane, last=doe (middle dropped)
    assert "jane.doe@acme.com" in out
    assert "jdoe@acme.com" in out


def test_accents_and_apostrophes_normalized():
    out = contacts.guess_emails("Renée O'Brien", "foo.io")
    assert out[0] == "renee.obrien@foo.io"


def test_single_name_only_first_pattern():
    out = contacts.guess_emails("Cher", "bar.com")
    assert out == ["cher@bar.com"]


def test_domain_normalized_lowercase():
    out = contacts.guess_emails("Jane Doe", "ACME.com")
    assert all(e.endswith("@acme.com") for e in out)


def test_empty_domain_or_name_returns_empty():
    assert contacts.guess_emails("Jane Doe", "") == []
    assert contacts.guess_emails("", "acme.com") == []
    assert contacts.guess_emails("   ", "acme.com") == []


def test_no_duplicates():
    out = contacts.guess_emails("Jane Doe", "acme.com")
    assert len(out) == len(set(out))
