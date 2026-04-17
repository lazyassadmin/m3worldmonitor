"""Congress.gov API client for members, bills, votes, and committee assignments."""

import asyncio
from datetime import date, datetime

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from poliwatch.config import settings
from poliwatch.models.bill import Bill
from poliwatch.models.member import CongressMember
from poliwatch.models.vote import Vote

BASE = "https://api.congress.gov/v3"
HEADERS = {"User-Agent": "PoliWatch/0.1.0 (open-source political accountability tool)"}


def _api_params(**kwargs) -> dict:
    p = {"api_key": settings.congress_api_key, "format": "json", **kwargs}
    return {k: v for k, v in p.items() if v is not None}


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


async def _get(client: httpx.AsyncClient, path: str, **params) -> dict:
    resp = await client.get(f"{BASE}/{path}", params=_api_params(**params), headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


async def ingest_members(db: AsyncSession) -> int:
    """Fetch all current members and upsert into DB."""
    if not settings.congress_api_key:
        logger.warning("CONGRESS_API_KEY not set; skipping member ingestion")
        return 0

    logger.info("Fetching Congress members from Congress.gov…")
    inserted = 0
    async with httpx.AsyncClient(timeout=30) as client:
        offset = 0
        limit = 250
        while True:
            data = await _get(client, "member", limit=limit, offset=offset, currentMember=True)
            members = data.get("members", [])
            if not members:
                break

            for m in members:
                bio_id = m.get("bioguideId")
                if not bio_id:
                    continue

                result = await db.execute(
                    select(CongressMember).where(CongressMember.bioguide_id == bio_id)
                )
                existing = result.scalar_one_or_none()

                terms = m.get("terms", {})
                if isinstance(terms, dict):
                    items = terms.get("item", [])
                else:
                    items = []
                chamber = "house"
                if items:
                    last_term = items[-1] if isinstance(items, list) else items
                    ch = (last_term.get("chamber") or "").lower()
                    if "senate" in ch:
                        chamber = "senate"

                if existing:
                    existing.name = m.get("name") or existing.name
                    existing.party = m.get("partyName") or existing.party
                    existing.state = m.get("state") or existing.state
                    existing.chamber = chamber
                else:
                    member = CongressMember(
                        bioguide_id=bio_id,
                        name=m.get("name") or "Unknown",
                        party=m.get("partyName") or "",
                        state=m.get("state") or "",
                        chamber=chamber,
                        committees=[],
                    )
                    db.add(member)
                    inserted += 1

            await db.flush()
            if len(members) < limit:
                break
            offset += limit
            await asyncio.sleep(0.5)  # be polite to the API

    await db.commit()
    logger.info(f"Member ingest complete: {inserted} new members")
    return inserted


async def ingest_committee_assignments(db: AsyncSession, bioguide_id: str) -> None:
    """Fetch and store committee assignments for one member."""
    if not settings.congress_api_key:
        return

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            data = await _get(client, f"member/{bioguide_id}/committee-assignment", limit=250)
        except httpx.HTTPStatusError as exc:
            logger.warning(f"Committee fetch failed for {bioguide_id}: {exc.response.status_code}")
            return

        committees = [
            c.get("name") or c.get("systemCode") or ""
            for c in data.get("committeeAssignments", [])
            if c.get("name") or c.get("systemCode")
        ]

    result = await db.execute(
        select(CongressMember).where(CongressMember.bioguide_id == bioguide_id)
    )
    member = result.scalar_one_or_none()
    if member:
        member.committees = committees
        await db.commit()


async def ingest_bills(db: AsyncSession, congress: int = 118, limit_per_type: int = 500) -> int:
    """Fetch recent bills and upsert into DB."""
    if not settings.congress_api_key:
        logger.warning("CONGRESS_API_KEY not set; skipping bill ingestion")
        return 0

    logger.info(f"Fetching bills for congress {congress}…")
    inserted = 0
    bill_types = ["hr", "s", "hres", "sres", "hjres", "sjres"]

    async with httpx.AsyncClient(timeout=60) as client:
        for bill_type in bill_types:
            offset = 0
            fetched = 0
            while fetched < limit_per_type:
                try:
                    data = await _get(
                        client,
                        f"bill/{congress}/{bill_type}",
                        limit=250,
                        offset=offset,
                        sort="updateDate+desc",
                    )
                except httpx.HTTPStatusError as exc:
                    logger.warning(f"Bill fetch failed ({bill_type}): {exc.response.status_code}")
                    break

                bills = data.get("bills", [])
                if not bills:
                    break

                for b in bills:
                    bill_number = b.get("number")
                    if not bill_number:
                        continue
                    bill_id = f"{congress}-{bill_type}-{bill_number}"

                    result = await db.execute(select(Bill).where(Bill.bill_id == bill_id))
                    if result.scalar_one_or_none():
                        continue

                    latest_action = b.get("latestAction") or {}
                    bill = Bill(
                        bill_id=bill_id,
                        congress=congress,
                        bill_type=bill_type,
                        bill_number=int(bill_number),
                        title=b.get("title") or "",
                        introduced_date=_parse_date(b.get("introducedDate")),
                        latest_action_date=_parse_date(latest_action.get("actionDate")),
                        subjects=[],
                        related_tickers=[],
                    )
                    db.add(bill)
                    inserted += 1
                    fetched += 1

                await db.flush()
                if len(bills) < 250 or fetched >= limit_per_type:
                    break
                offset += 250
                await asyncio.sleep(0.3)

    await db.commit()
    logger.info(f"Bill ingest complete: {inserted} new bills")
    return inserted


async def ingest_votes(db: AsyncSession, bioguide_id: str, congress: int = 118) -> int:
    """Fetch recent votes for a member from ProPublica (fallback) or Congress.gov."""
    # Congress.gov v3 doesn't have a per-member vote roll easily; use member's recent votes
    # This is a best-effort implementation using available endpoints
    if not settings.propublica_api_key:
        return 0

    inserted = 0
    headers = {**HEADERS, "X-API-Key": settings.propublica_api_key}
    url = f"https://api.propublica.org/congress/v1/members/{bioguide_id}/votes.json"

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(url, headers=headers, params={"offset": 0})
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning(f"Vote fetch failed for {bioguide_id}: {exc}")
            return 0

        votes_data = (data.get("results") or [{}])[0].get("votes") or []
        for v in votes_data:
            bill_info = v.get("bill") or {}
            bill_id_raw = bill_info.get("bill_id") or ""
            if not bill_id_raw:
                continue

            # ProPublica format: "hr1234-118" → normalize to our format
            parts = bill_id_raw.rsplit("-", 1)
            if len(parts) == 2:
                bill_id = f"{parts[1]}-{parts[0]}"
            else:
                bill_id = bill_id_raw

            vote_date = _parse_date(v.get("date"))
            if not vote_date:
                continue

            position = (v.get("position") or "").lower()

            existing = await db.execute(
                select(Vote).where(
                    Vote.member_id == bioguide_id,
                    Vote.bill_id == bill_id,
                    Vote.vote_date == vote_date,
                )
            )
            if existing.scalar_one_or_none():
                continue

            vote = Vote(
                member_id=bioguide_id,
                bill_id=bill_id,
                vote_date=vote_date,
                vote_position=position or "not voting",
            )
            db.add(vote)
            inserted += 1

        await db.flush()

    await db.commit()
    return inserted
