"""Trade-to-legislation correlation engine."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from poliwatch.models.bill import Bill
from poliwatch.models.member import CongressMember
from poliwatch.models.trade import StockTrade

# Sector keywords that map to committee names (simplified)
SECTOR_COMMITTEE_KEYWORDS: dict[str, list[str]] = {
    "financial": ["financial services", "banking", "finance"],
    "energy": ["energy", "natural resources", "environment"],
    "tech": ["science", "technology", "commerce", "innovation"],
    "defense": ["armed services", "defense", "homeland security"],
    "healthcare": ["health", "education", "labor"],
    "agriculture": ["agriculture", "food"],
    "transportation": ["transportation", "infrastructure"],
}


def _ticker_keywords(ticker: str, asset_name: str) -> list[str]:
    """Return lowercase search terms for a traded asset."""
    terms = [ticker.lower()]
    for word in asset_name.lower().split():
        if len(word) > 3:
            terms.append(word)
    return terms


def _bill_matches_asset(bill: Bill, ticker: str, asset_name: str) -> bool:
    """True if a bill's title/subjects overlap with the traded asset."""
    keywords = _ticker_keywords(ticker, asset_name)
    text = (bill.title + " " + " ".join(bill.subjects or [])).lower()
    return any(kw in text for kw in keywords)


def _member_committee_overlaps_bill(member: CongressMember, bill: Bill) -> bool:
    """True if the member sits on a committee with jurisdiction over the bill."""
    committees_lower = " ".join(member.committees or []).lower()
    bill_text = (bill.title + " " + " ".join(bill.subjects or [])).lower()
    for _sector, keywords in SECTOR_COMMITTEE_KEYWORDS.items():
        sector_in_committee = any(kw in committees_lower for kw in keywords)
        sector_in_bill = any(kw in bill_text for kw in keywords)
        if sector_in_committee and sector_in_bill:
            return True
    return False


async def correlate_trade_to_legislation(
    trade: StockTrade, db: AsyncSession, window_days: int = 30
) -> list[Bill]:
    """
    Find bills that:
    1. Were introduced or had major action within `window_days` BEFORE the trade
    2. Are in a committee the member sits on
    3. Have subjects or keywords matching the traded ticker/company

    Returns ranked list of correlated bills (highest relevance first).
    """
    member_result = await db.execute(
        select(CongressMember).where(CongressMember.bioguide_id == trade.member_id)
    )
    member = member_result.scalar_one_or_none()

    window_start = trade.trade_date - timedelta(days=window_days)
    window_end = trade.trade_date + timedelta(days=window_days)

    bill_result = await db.execute(
        select(Bill).where(
            Bill.latest_action_date >= window_start,
            Bill.latest_action_date <= window_end,
        )
    )
    candidate_bills = list(bill_result.scalars().all())

    scored: list[tuple[int, Bill]] = []
    for bill in candidate_bills:
        score = 0
        if _bill_matches_asset(bill, trade.ticker, trade.asset_name):
            score += 2
        if member and _member_committee_overlaps_bill(member, bill):
            score += 1
        if score > 0:
            scored.append((score, bill))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [b for _, b in scored]
