"""Sector → ticker lookup + fuzzy company-name matcher for bill text."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz

from poliwatch.config import REPO_ROOT

_SECTOR_FILE = REPO_ROOT / "data" / "sector_tickers.json"


@dataclass(frozen=True, slots=True)
class TickerMatch:
    ticker: str
    sector: str
    score: float  # 0–100
    matched_on: str  # "keyword" | "company"


@lru_cache(maxsize=1)
def _load_sectors() -> dict[str, dict]:
    if not _SECTOR_FILE.exists():
        return {}
    return json.loads(_SECTOR_FILE.read_text(encoding="utf-8"))


def sector_for_ticker(ticker: str) -> str | None:
    ticker = ticker.upper()
    for sector_name, data in _load_sectors().items():
        if ticker in data.get("tickers", {}):
            return sector_name
    return None


def sectors_for_committee(committee_name: str) -> set[str]:
    """Heuristic: map a committee name to the sectors it most plausibly oversees."""
    name = committee_name.lower()
    hits: set[str] = set()
    mapping = {
        "armed services": {"defense"},
        "intelligence": {"defense", "technology"},
        "homeland security": {"defense", "technology"},
        "veterans": {"defense", "healthcare"},
        "foreign affairs": {"defense", "energy"},
        "foreign relations": {"defense", "energy"},
        "financial services": {"financial", "crypto"},
        "banking": {"financial", "crypto"},
        "ways and means": {"financial", "healthcare"},
        "finance": {"financial", "healthcare"},
        "judiciary": {"technology", "crypto"},
        "energy and commerce": {"energy", "clean_energy", "healthcare", "telecom", "technology"},
        "energy and natural resources": {"energy", "clean_energy"},
        "natural resources": {"energy", "clean_energy"},
        "environment": {"energy", "clean_energy"},
        "agriculture": {"consumer"},
        "commerce": {"technology", "telecom", "transportation", "consumer"},
        "science, space": {"technology", "defense"},
        "transportation": {"transportation"},
        "small business": {"consumer"},
        "health": {"healthcare"},
        "labor": {"healthcare", "consumer"},
        "education": {"consumer"},
        "oversight": {"technology", "financial"},
    }
    for key, sectors in mapping.items():
        if key in name:
            hits.update(sectors)
    return hits


def tickers_for_sectors(sectors: set[str]) -> set[str]:
    out: set[str] = set()
    data = _load_sectors()
    for sector in sectors:
        out.update(data.get(sector, {}).get("tickers", {}).keys())
    return out


def match_bill_text_to_tickers(
    text: str,
    *,
    subjects: list[str] | None = None,
    min_score: float = 88.0,
) -> list[TickerMatch]:
    """Return ticker matches for a bill's title + subjects.

    Combines two strategies:
      1. Subject keyword → sector → all tickers in that sector (exact).
      2. Fuzzy company-name match via rapidfuzz (min_score default 88).
    """
    data = _load_sectors()
    hay = (text or "").lower()
    subject_hay = " ".join(s.lower() for s in (subjects or []))
    full_hay = f"{hay} {subject_hay}".strip()

    matches: dict[str, TickerMatch] = {}

    for sector, sector_data in data.items():
        for keyword in sector_data.get("keywords", []):
            if keyword.lower() in full_hay:
                for ticker in sector_data.get("tickers", {}):
                    matches.setdefault(
                        ticker,
                        TickerMatch(ticker=ticker, sector=sector, score=100.0, matched_on="keyword"),
                    )
                break  # one keyword hit per sector is enough

        for ticker, aliases in sector_data.get("tickers", {}).items():
            for alias in aliases:
                score = fuzz.partial_ratio(alias.lower(), hay)
                if score >= min_score:
                    existing = matches.get(ticker)
                    if existing is None or score > existing.score:
                        matches[ticker] = TickerMatch(
                            ticker=ticker,
                            sector=sector,
                            score=float(score),
                            matched_on="company",
                        )

    return sorted(matches.values(), key=lambda m: m.score, reverse=True)
