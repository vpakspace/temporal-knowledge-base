"""Tests for entity resolution (name normalization)."""

from temporal.resolution import EntityResolver


def test_normalize_corp():
    assert EntityResolver._normalize_name("IBM Corp.") == "ibm"


def test_normalize_inc():
    assert EntityResolver._normalize_name("Apple Inc.") == "apple"


def test_normalize_ltd():
    assert EntityResolver._normalize_name("Tesco Ltd.") == "tesco"


def test_normalize_llc():
    assert EntityResolver._normalize_name("Acme LLC") == "acme"


def test_normalize_whitespace():
    assert EntityResolver._normalize_name("  IBM   Corp  ") == "ibm"


def test_normalize_case():
    assert (
        EntityResolver._normalize_name("International Business Machines")
        == "international business machines"
    )


def test_normalize_plain():
    assert EntityResolver._normalize_name("Google") == "google"
