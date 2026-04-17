"""Congress.gov API client — members, committees, bills, votes.

https://api.congress.gov/v3/

Degrades gracefully if CONGRESS_API_KEY is unset.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import httpx
from loguru import logger
from sqlalchemy.orm import Session

from poliwatch.config import get_settings
from poliwatch.ingestion._amounts import parse_date
from poliwatch.ingestion._health import mark_degraded, mark_success
from poliwatch.ingestion._http import fetch_json
from poliwatch.ingestion._tickers import match_bill_text_to_tickers
from poliwatch.ingestion._upsert import upsert_member
from poliwatch.models.bill import Bill
from poliwatch.models.vote import Vote, VotePosition

BASE = "https://api.congress.gov/v3"
SOURCE_MEMBERS = "congress_api_members"
SOURCE_BILLS = "congress_api_bills"
SOURCE_VOTES = "congress_api_votes"


def _auth_params(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = get_settings()
    params = {"api_key": settings.congress_api_key, "format": "json"}
    if extra:
        params.update(extra)
    return params


async def _paginate(url: str, root_key: str, *, limit: int = 250, max_pages: int = 40) -> list[dict]:
    """Walk the ``pagination.next`` chain, collecting ``root_key`` items."""
    out: list[dict] = []
    offset = 0
    for _ in range(max_pages):
        try:
            data = await fetch_json(
                url, params=_auth_params({"limit": limit, "offset": offset})
            )
        except httpx.HTTPStatusError as exc:
            logger.warning("congress.gov {} → {}", url, exc.response.status_code)
            break
        items = data.get(root_key) or []
        if isinstance(items, dict):
            items = list(items.values())
        if not items:
            break
        out.extend(items)
        if "pagination" not in data or "next" not in (data["pagination"] or {}):
            break
        offset += limit
    return out


# --------------------------------------------------------------------------- members

async def ingest_members(db: Session, *, current_congress: int = 118) -> int:
    settings = get_settings()
    if not settings.has_congress_api:
        mark_degraded(db, SOURCE_MEMBERS, "CONGRESS_API_KEY not set")
        return 0

    logger.info("[congress_api] fetching members for congress {}", current_congress)
    try:
        items = await _paginate(
            f"{BASE}/member/congress/{current_congress}", "members", limit=250
        )
    except Exception as exc:  # noqa: BLE001
        mark_degraded(db, SOURCE_MEMBERS, f"fetch failed: {exc}")
        return 0

    count = 0
    for m in items:
        bioguide = m.get("bioguideId")
        if not bioguide:
            continue
        name_parts = m.get("name", "").split(", ")
        name = (
            f"{name_parts[1]} {name_parts[0]}".strip()
            if len(name_parts) == 2
            else m.get("name", "").strip()
        )
        terms = m.get("terms", {}).get("item", []) or []
        chamber = "senate" if any("Senate" in (t.get("chamber") or "") for t in terms) else "house"
        party = (m.get("partyName") or "").strip() or None
        state = (m.get("state") or "")[:4] or None

        upsert_member(
            db,
            bioguide_id=bioguide,
            name=name,
            party=party,
            state=state,
            chamber=chamber,
        )
        count += 1

    db.commit()
    await _ingest_committee_assignments(db)
    mark_success(db, SOURCE_MEMBERS, count)
    return count


async def _ingest_committee_assignments(db: Session) -> None:
    """Attach committee names to each member. One request per member — uses semaphore."""
    from poliwatch.models.member import CongressMember  # local to avoid circular

    members = db.query(CongressMember).all()
    for member in members:
        try:
            data = await fetch_json(
                f"{BASE}/member/{member.bioguide_id}",
                params=_auth_params(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("committee fetch skipped for {}: {}", member.bioguide_id, exc)
            continue
        raw = data.get("member") or {}
        assignments = raw.get("committeeAssignments") or {}
        items = assignments.get("item") or assignments.get("committee") or []
        if isinstance(items, dict):
            items = [items]
        names: list[str] = []
        for item in items:
            nm = item.get("name") if isinstance(item, dict) else None
            if nm:
                names.append(nm)
        if names:
            member.committees = sorted(set(names))
            db.add(member)
    db.commit()


# --------------------------------------------------------------------------- bills

def _normalize_bill_id(congress: int, bill_type: str, bill_number: int | str) -> str:
    return f"{congress}-{bill_type.lower()}-{bill_number}"


async def ingest_recent_bills(
    db: Session, *, congress: int = 118, limit: int = 250, max_pages: int = 8
) -> int:
    settings = get_settings()
    if not settings.has_congress_api:
        mark_degraded(db, SOURCE_BILLS, "CONGRESS_API_KEY not set")
        return 0

    logger.info("[congress_api] fetching recent bills for congress {}", congress)
    try:
        items = await _paginate(
            f"{BASE}/bill/{congress}", "bills", limit=limit, max_pages=max_pages
        )
    except Exception as exc:  # noqa: BLE001
        mark_degraded(db, SOURCE_BILLS, f"fetch failed: {exc}")
        return 0

    created = 0
    for b in items:
        bill_type = (b.get("type") or "").lower()
        bill_number = b.get("number")
        if not bill_type or bill_number is None:
            continue
        bill_id = _normalize_bill_id(congress, bill_type, bill_number)

        title = (b.get("title") or "").strip()[:1000]
        introduced = parse_date(b.get("introducedDate"))
        latest_action = b.get("latestAction") or {}
        latest_d = parse_date(latest_action.get("actionDate"))
        latest_text = (latest_action.get("text") or "")[:1000] or None

        subjects = _subjects_from(b)
        matches = match_bill_text_to_tickers(title, subjects=subjects)
        related_tickers = sorted({m.ticker for m in matches})

        existing = db.get(Bill, bill_id)
        if existing is None:
            db.add(
                Bill(
                    bill_id=bill_id,
                    congress=congress,
                    bill_type=bill_type,
                    bill_number=int(bill_number),
                    title=title,
                    introduced_date=introduced,
                    latest_action_date=latest_d,
                    latest_action_text=latest_text,
                    subjects=subjects,
                    related_tickers=related_tickers,
                )
            )
            created += 1
        else:
            existing.title = title or existing.title
            existing.latest_action_date = latest_d or existing.latest_action_date
            existing.latest_action_text = latest_text or existing.latest_action_text
            if subjects:
                existing.subjects = subjects
            if related_tickers:
                existing.related_tickers = related_tickers
            db.add(existing)

    db.commit()
    mark_success(db, SOURCE_BILLS, created)
    return created


def _subjects_from(b: dict[str, Any]) -> list[str]:
    subs = b.get("subjects") or {}
    legislative = subs.get("legislativeSubjects") if isinstance(subs, dict) else None
    items = []
    if isinstance(legislative, dict):
        items = legislative.get("item") or []
    elif isinstance(legislative, list):
        items = legislative
    names = []
    for item in items:
        if isinstance(item, dict) and item.get("name"):
            names.append(item["name"])
    policy = subs.get("policyArea") if isinstance(subs, dict) else None
    if isinstance(policy, dict) and policy.get("name"):
        names.append(policy["name"])
    return sorted(set(names))


# --------------------------------------------------------------------------- votes

_POSITION_MAP = {
    "yea": VotePosition.YES,
    "yes": VotePosition.YES,
    "aye": VotePosition.YES,
    "nay": VotePosition.NO,
    "no": VotePosition.NO,
    "present": VotePosition.PRESENT,
    "not voting": VotePosition.NOT_VOTING,
    "abstain": VotePosition.ABSTAIN,
}


async def ingest_recent_votes(db: Session, *, congress: int = 118) -> int:
    settings = get_settings()
    if not settings.has_congress_api:
        mark_degraded(db, SOURCE_VOTES, "CONGRESS_API_KEY not set")
        return 0

    count = 0
    for chamber in ("house", "senate"):
        try:
            data = await fetch_json(
                f"{BASE}/congress/{congress}/{chamber}/vote",
                params=_auth_params({"limit": 100}),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("votes list failed for {}: {}", chamber, exc)
            continue
        votes = data.get("votes") or []
        for v in votes:
            roll = v.get("rollCall") or v.get("rollNumber")
            session = v.get("session") or v.get("sessionNumber")
            if roll is None or session is None:
                continue
            try:
                detail = await fetch_json(
                    f"{BASE}/congress/{congress}/{chamber}/vote/{session}/{roll}",
                    params=_auth_params(),
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("vote detail skipped: {}", exc)
                continue
            count += _persist_vote_detail(db, detail, congress=congress)
    db.commit()
    mark_success(db, SOURCE_VOTES, count)
    return count


def _persist_vote_detail(db: Session, detail: dict, *, congress: int) -> int:
    root = detail.get("vote") or detail
    date_str = root.get("date") or root.get("voteDate")
    vote_d: date | None = parse_date(date_str) or (
        datetime.utcnow().date() if date_str is None else None
    )
    bill_info = root.get("bill") or {}
    bill_type = (bill_info.get("type") or "").lower()
    bill_number = bill_info.get("number")
    if not bill_type or bill_number is None or vote_d is None:
        return 0
    bill_id = _normalize_bill_id(congress, bill_type, bill_number)

    if db.get(Bill, bill_id) is None:
        # Create a thin Bill row so the FK is satisfied; fleshed out later.
        db.add(
            Bill(
                bill_id=bill_id,
                congress=congress,
                bill_type=bill_type,
                bill_number=int(bill_number),
                title=(bill_info.get("title") or bill_id)[:1000],
                subjects=[],
                related_tickers=[],
            )
        )
        db.flush()

    persisted = 0
    for pos in root.get("positions", []) or []:
        if not isinstance(pos, dict):
            continue
        bioguide = pos.get("bioguideId")
        raw_pos = (pos.get("votePosition") or pos.get("voteCast") or "").lower()
        mapped = _POSITION_MAP.get(raw_pos, VotePosition.NOT_VOTING)
        if not bioguide:
            continue
        # Avoid duplicates via unique constraint; use an upsert-ish check.
        existing = (
            db.query(Vote)
            .filter(
                Vote.member_id == bioguide,
                Vote.bill_id == bill_id,
                Vote.vote_date == vote_d,
            )
            .first()
        )
        if existing is not None:
            if existing.vote_position != mapped:
                existing.vote_position = mapped
                db.add(existing)
            continue
        db.add(
            Vote(
                member_id=bioguide,
                bill_id=bill_id,
                vote_date=vote_d,
                vote_position=mapped,
            )
        )
        persisted += 1
    return persisted
