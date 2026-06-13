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


def test_strips_trailing_credentials():
    # "Jeremy Schrooten, PhD" must guess from the surname, not the credential.
    assert contacts.guess_emails("Jeremy Schrooten, PhD", "acme.com")[0] == "jeremy.schrooten@acme.com"
    assert contacts.guess_emails("Dr. Vikram Rao", "acme.com")[0] == "vikram.rao@acme.com"
    assert contacts.guess_emails("Sarah Lee Jr.", "acme.com")[0] == "sarah.lee@acme.com"


def test_real_surname_not_mistaken_for_credential():
    # A short real surname (e.g. "Ma") must survive.
    assert contacts.guess_emails("Jack Ma", "acme.com")[0] == "jack.ma@acme.com"


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


def test_is_credentialed_local_part_flags_credentials():
    # Credentials/titles leaking into the local-part should be flagged.
    assert contacts.is_credentialed_local_part("jeremy.phd@acme.com")
    assert contacts.is_credentialed_local_part("phd@acme.com")
    assert contacts.is_credentialed_local_part("dr.smith@acme.com")
    assert contacts.is_credentialed_local_part("jane-md@acme.com")


def test_is_credentialed_local_part_allows_real_addresses():
    assert not contacts.is_credentialed_local_part("jeremy.schrooten@acme.com")
    assert not contacts.is_credentialed_local_part("info@acme.com")
    assert not contacts.is_credentialed_local_part("jane.doe@acme.com")
