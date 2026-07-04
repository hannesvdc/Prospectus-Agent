"""Tests for deterministic email-pattern guessing."""
from __future__ import annotations

from prospectus_agent import contacts


def test_basic_patterns_and_order():
    out = contacts.guess_emails("Jane Doe", "acme.com")
    # Wider net of common corporate formats, most-likely first.
    assert out == [
        "jane.doe@acme.com",
        "jdoe@acme.com",
        "janedoe@acme.com",
        "jane@acme.com",
        "j.doe@acme.com",
        "jane_doe@acme.com",
        "janed@acme.com",
        "doe.jane@acme.com",
        "doe@acme.com",
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


# --- pattern inference / application (learn a domain's format from real addresses) ---

def test_infer_pattern_first_dot_last():
    known = [("Jane Doe", "jane.doe@acme.com")]
    assert contacts.infer_pattern(known, "acme.com") == "first.last"


def test_infer_pattern_filast():
    # dalpern@ for Dan Alpern -> {first-initial}{last}
    known = [("Dan Alpern", "dalpern@batterystreak.com")]
    assert contacts.infer_pattern(known, "batterystreak.com") == "filast"


def test_infer_pattern_majority_vote():
    known = [
        ("Jane Doe", "jdoe@acme.com"),      # filast
        ("Bob Smith", "bsmith@acme.com"),   # filast
        ("Al Roe", "al.roe@acme.com"),      # first.last (outvoted)
    ]
    assert contacts.infer_pattern(known, "acme.com") == "filast"


def test_infer_pattern_ignores_other_domains():
    # a personal address on another domain tells us nothing about acme.com
    known = [("Jane Doe", "jane.doe@gmail.com")]
    assert contacts.infer_pattern(known, "acme.com") is None


def test_infer_then_apply_builds_correct_address():
    known = [("Dan Alpern", "dalpern@batterystreak.com")]
    pat = contacts.infer_pattern(known, "batterystreak.com")
    # apply the learned format to a different person on the same domain
    assert contacts.apply_pattern("Randy Lowe", "batterystreak.com", pat) == "rlowe@batterystreak.com"


def test_apply_pattern_needs_surname_returns_empty():
    # "last.first" can't be built for a single-name person
    assert contacts.apply_pattern("Cher", "acme.com", "last.first") == ""


def test_infer_pattern_empty_known_returns_none():
    assert contacts.infer_pattern([], "acme.com") is None


# --- is_real_email: reject obfuscation placeholders & malformed addresses ---

def test_is_real_email_accepts_normal():
    assert contacts.is_real_email("info@acme.com")
    assert contacts.is_real_email("jane.doe@sub.acme.co.uk")


def test_is_real_email_rejects_cloudflare_placeholder():
    assert not contacts.is_real_email("[email protected]")
    assert not contacts.is_real_email("[email protected]")


def test_is_real_email_rejects_malformed():
    for bad in ["", "  ", "notanemail", "no@domain", "two@@at.com", "@acme.com", "a@b"]:
        assert not contacts.is_real_email(bad), bad


def test_is_real_email_rejects_credentialed_local():
    assert not contacts.is_real_email("jeremy.phd@acme.com")
