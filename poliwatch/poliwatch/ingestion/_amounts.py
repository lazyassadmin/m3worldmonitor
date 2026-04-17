"""Parse STOCK Act amount ranges (e.g. '$1,001 - $15,000') and trade types."""

from __future__ import annotations

import re
from datetime import date, datetime

from poliwatch.models.trade import TradeType

_AMOUNT_RE = re.compile(r"\$?\s*([\d,]+)(?:\s*(?:-|to|–)\s*\$?\s*([\d,]+))?", re.IGNORECASE)
# Canonical STOCK Act buckets for House/Senate reports.
_CANONICAL_BUCKETS: list[tuple[str, int, int]] = [
    ("$1,001 - $15,000", 1001, 15000),
    ("$15,001 - $50,000", 15001, 50000),
    ("$50,001 - $100,000", 50001, 100000),
    ("$100,001 - $250,000", 100001, 250000),
    ("$250,001 - $500,000", 250001, 500000),
    ("$500,001 - $1,000,000", 500001, 1000000),
    ("$1,000,001 - $5,000,000", 1000001, 5000000),
    ("$5,000,001 - $25,000,000", 5000001, 25000000),
    ("$25,000,001 - $50,000,000", 25000001, 50000000),
    ("Over $50,000,000", 50000001, 100000000),
]


def parse_amount_range(raw: str | None) -> tuple[int | None, int | None, str | None]:
    """Return (min, max, canonical_label) for a free-form amount string."""
    if not raw:
        return None, None, None
    text = raw.strip()
    # Try canonical bucket first (case-insensitive)
    lowered = text.lower()
    for label, lo, hi in _CANONICAL_BUCKETS:
        if label.lower() in lowered or lowered in label.lower():
            return lo, hi, label

    match = _AMOUNT_RE.search(text)
    if not match:
        return None, None, text

    try:
        lo = int(match.group(1).replace(",", ""))
    except (TypeError, ValueError):
        return None, None, text
    hi_s = match.group(2)
    hi = int(hi_s.replace(",", "")) if hi_s else lo
    # Snap to a canonical bucket when close enough.
    for label, clo, chi in _CANONICAL_BUCKETS:
        if clo <= lo <= chi or clo <= hi <= chi:
            return max(clo, lo), min(chi, hi) if hi >= clo else chi, label
    return lo, hi, text


def parse_trade_type(raw: str | None) -> TradeType:
    if not raw:
        return TradeType.OTHER
    t = raw.strip().lower()
    if "purchase" in t or t.startswith("p") or "buy" in t:
        return TradeType.PURCHASE
    if "exchange" in t or t.startswith("e"):
        return TradeType.EXCHANGE
    if "partial" in t or "s (partial)" in t:
        return TradeType.SALE_PARTIAL
    if "full" in t or "s (full)" in t:
        return TradeType.SALE_FULL
    if "sale" in t or t.startswith("s"):
        return TradeType.SALE
    return TradeType.OTHER


_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d %B %Y", "%B %d, %Y")


def parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def disclosure_delay(trade_d: date | None, disclosure_d: date | None) -> int | None:
    if trade_d is None or disclosure_d is None:
        return None
    return (disclosure_d - trade_d).days
