from datetime import datetime, timedelta, timezone

import pytest

from app.services.analytics import bucket_stats, detect_anomalies, to_frame

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def rows(values, minutes=1):
    return [(START + timedelta(minutes=i * minutes), v) for i, v in enumerate(values)]


def test_bucket_stats_groups_by_hour():
    df = to_frame(rows([1.0] * 60 + [3.0] * 60))
    points = bucket_stats(df, "1h")
    assert [(p["count"], p["mean"]) for p in points] == [(60, 1.0), (60, 3.0)]


def test_bucket_stats_skips_empty_buckets():
    df = to_frame([(START, 1.0), (START + timedelta(hours=5), 2.0)])
    assert len(bucket_stats(df, "1h")) == 2


def test_bucket_stats_rejects_unknown_bucket():
    with pytest.raises(ValueError):
        bucket_stats(to_frame(rows([1.0])), "2h")


def test_empty_frame():
    df = to_frame([])
    assert bucket_stats(df, "1h") == []
    assert detect_anomalies(df) == []


def test_detects_spike_and_drop_not_normal_noise():
    values = [50 + (i % 5) * 0.2 for i in range(60)]
    values[40] = 70.0
    values[50] = 30.0
    found = detect_anomalies(to_frame(rows(values)), window=20, threshold=3.0)
    assert [a["value"] for a in found] == [70.0, 30.0]
    assert found[0]["z_score"] > 3
    assert found[1]["z_score"] < -3


def test_spike_after_flat_baseline_is_flagged():
    values = [10.0] * 10 + [11.0]
    found = detect_anomalies(to_frame(rows(values)), window=5)
    assert [a["value"] for a in found] == [11.0]


def test_too_few_points_returns_nothing():
    assert detect_anomalies(to_frame(rows([1.0, 100.0])), window=5) == []


def test_window_must_be_at_least_three():
    with pytest.raises(ValueError):
        detect_anomalies(to_frame(rows([1.0] * 10)), window=2)
