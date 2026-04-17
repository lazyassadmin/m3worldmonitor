"""Tests for ingestion helpers."""

from datetime import date

import pytest

from poliwatch.ingestion.quiver import _parse_amount, _parse_date


def test_parse_date_iso():
    assert _parse_date("2024-03-15") == date(2024, 3, 15)


def test_parse_date_us():
    assert _parse_date("03/15/2024") == date(2024, 3, 15)


def test_parse_date_none():
    assert _parse_date(None) is None
    assert _parse_date("") is None


def test_parse_amount_known():
    lo, hi = _parse_amount("$15,001 - $50,000")
    assert lo == 15001
    assert hi == 50000


def test_parse_amount_unknown():
    lo, hi = _parse_amount("Unknown amount")
    assert lo is None
    assert hi is None


def test_parse_amount_case_insensitive():
    lo, hi = _parse_amount("$1,001 - $15,000".lower())
    assert lo == 1001
