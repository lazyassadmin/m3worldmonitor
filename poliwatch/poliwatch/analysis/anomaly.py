"""Statistical anomaly detection helpers (Z-score, outlier flagging)."""

import numpy as np
import pandas as pd


def compute_zscore_outliers(scores: list[float], threshold: float = 2.0) -> list[bool]:
    """Return bool mask: True where score is an outlier (z-score > threshold)."""
    if len(scores) < 3:
        return [False] * len(scores)
    arr = np.array(scores, dtype=float)
    mean, std = arr.mean(), arr.std()
    if std == 0:
        return [False] * len(scores)
    z = np.abs((arr - mean) / std)
    return (z > threshold).tolist()


def build_trade_dataframe(trades: list[dict]) -> pd.DataFrame:
    """Convert a list of trade dicts to a DataFrame for analysis."""
    return pd.DataFrame(trades)


def disclosure_delay_distribution(trades: list[dict]) -> dict:
    """Summary stats for disclosure delay."""
    df = build_trade_dataframe(trades)
    if df.empty or "disclosure_delay_days" not in df.columns:
        return {}
    col = df["disclosure_delay_days"].dropna()
    return {
        "mean": float(col.mean()),
        "median": float(col.median()),
        "p90": float(col.quantile(0.9)),
        "p99": float(col.quantile(0.99)),
        "over_30": int((col > 30).sum()),
        "over_45": int((col > 45).sum()),
    }


def top_suspicious_members(trades: list[dict], top_n: int = 10) -> list[dict]:
    """Rank members by average suspicion score."""
    df = build_trade_dataframe(trades)
    if df.empty or "member_id" not in df.columns:
        return []
    grp = (
        df.groupby("member_id")["suspicion_score"]
        .agg(["mean", "count", "max"])
        .reset_index()
        .rename(columns={"mean": "avg_score", "count": "trade_count", "max": "max_score"})
        .sort_values("avg_score", ascending=False)
        .head(top_n)
    )
    return grp.to_dict(orient="records")
