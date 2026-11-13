"""Time-series analytics with pandas: bucketed stats and anomaly detection."""

from datetime import datetime

import numpy as np
import pandas as pd

BUCKETS = {"1min": "1min", "5min": "5min", "15min": "15min", "1h": "1h", "1d": "1D"}


def to_frame(rows: list[tuple[datetime, float]]) -> pd.DataFrame:
    """Build a time-indexed DataFrame from (timestamp, value) rows."""
    df = pd.DataFrame(rows, columns=["ts", "value"])
    if df.empty:
        return df.set_index(pd.DatetimeIndex([], tz="UTC", name="ts"))
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.sort_values("ts").set_index("ts")


def bucket_stats(df: pd.DataFrame, bucket: str) -> list[dict]:
    """Resample readings into fixed time buckets with count / mean / min / max."""
    if bucket not in BUCKETS:
        raise ValueError(f"bucket must be one of {', '.join(BUCKETS)}")
    if df.empty:
        return []
    grouped = df["value"].resample(BUCKETS[bucket]).agg(["count", "mean", "min", "max"])
    grouped = grouped[grouped["count"] > 0]
    return [
        {
            "bucket": idx.to_pydatetime(),
            "count": int(row["count"]),
            "mean": round(float(row["mean"]), 4),
            "min": float(row["min"]),
            "max": float(row["max"]),
        }
        for idx, row in grouped.iterrows()
    ]


def detect_anomalies(df: pd.DataFrame, window: int = 20, threshold: float = 3.0) -> list[dict]:
    """Flag readings far from the recent baseline using a rolling z-score.

    The baseline for each point uses only the *previous* ``window`` readings
    (``shift(1)``), so a spike cannot hide itself by inflating its own mean.
    """
    if window < 3:
        raise ValueError("window must be at least 3")
    if len(df) <= window:
        return []

    values = df["value"]
    baseline = values.shift(1).rolling(window=window, min_periods=window)
    mean = baseline.mean()
    # A perfectly flat baseline has std 0. Flooring it makes any change from
    # that baseline score very high, while an unchanged value scores 0.
    std = baseline.std().clip(lower=1e-9)
    z = ((values - mean) / std).clip(-999, 999)

    flagged = (z.abs() >= threshold).fillna(False).to_numpy()
    return [
        {
            "ts": ts.to_pydatetime(),
            "value": float(values.loc[ts]),
            "rolling_mean": round(float(mean.loc[ts]), 4),
            "z_score": round(float(z.loc[ts]), 2),
        }
        for ts in df.index[flagged]
    ]
