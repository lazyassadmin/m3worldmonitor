"""Tests for analysis helpers."""

import pytest

from poliwatch.analysis.anomaly import compute_zscore_outliers, disclosure_delay_distribution


def test_zscore_outliers_basic():
    scores = [10.0, 12.0, 11.0, 90.0]  # 90 is a clear outlier
    result = compute_zscore_outliers(scores)
    assert result[-1] is True  # 90 should be flagged
    assert result[0] is False


def test_zscore_outliers_too_few():
    assert compute_zscore_outliers([50.0, 60.0]) == [False, False]


def test_zscore_outliers_uniform():
    scores = [50.0] * 10
    assert all(not x for x in compute_zscore_outliers(scores))


def test_disclosure_delay_distribution():
    trades = [
        {"disclosure_delay_days": 5},
        {"disclosure_delay_days": 10},
        {"disclosure_delay_days": 35},
        {"disclosure_delay_days": 50},
    ]
    stats = disclosure_delay_distribution(trades)
    assert stats["over_30"] == 2
    assert stats["over_45"] == 1
    assert stats["mean"] == pytest.approx(25.0)
