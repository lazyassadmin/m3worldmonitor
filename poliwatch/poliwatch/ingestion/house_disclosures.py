"""House Financial Disclosure XML ingestion.

Bulk ZIP archive: https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{YEAR}FD.zip
Each ZIP contains ``{YEAR}FD.xml`` with filing metadata. Transaction-level
detail lives in the per-filing PDF (parsed in a future task).

For now we land the filing metadata — filer name, filing type (P = PTR),
docID → URL — which is enough to surface disclosure-delay context on
members even when Quiver is down.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date
from typing import Any

from loguru import logger
from lxml import etree
from sqlalchemy.orm import Session

from poliwatch.ingestion._amounts import parse_date
from poliwatch.ingestion._health import mark_degraded, mark_success
from poliwatch.ingestion._http import fetch_bytes
from poliwatch.ingestion._upsert import ensure_placeholder_member

SOURCE = "house"
ZIP_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
PDF_URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"


def _iter_filings(xml_bytes: bytes) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    root = etree.fromstring(xml_bytes)
    for member in root.findall(".//Member"):
        filing: dict[str, Any] = {}
        for child in member:
            tag = etree.QName(child.tag).localname
            filing[tag] = (child.text or "").strip() if child.text else ""
        out.append(filing)
    return out


def _full_name(filing: dict[str, Any]) -> str:
    prefix = filing.get("Prefix", "")
    first = filing.get("First", "")
    last = filing.get("Last", "")
    suffix = filing.get("Suffix", "")
    return " ".join(p for p in (prefix, first, last, suffix) if p).strip()


async def ingest_house_filings(db: Session, *, year: int) -> int:
    url = ZIP_URL.format(year=year)
    logger.info("[house] downloading {}", url)
    try:
        blob = await fetch_bytes(url)
    except Exception as exc:  # noqa: BLE001
        mark_degraded(db, SOURCE, f"fetch {year} failed: {exc}")
        return 0

    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            xml_name = next((n for n in zf.namelist() if n.endswith(".xml")), None)
            if xml_name is None:
                mark_degraded(db, SOURCE, f"no .xml inside {year}FD.zip")
                return 0
            xml_bytes = zf.read(xml_name)
    except zipfile.BadZipFile as exc:
        mark_degraded(db, SOURCE, f"bad zip {year}: {exc}")
        return 0

    filings = _iter_filings(xml_bytes)
    ptr_filings = [
        f for f in filings if (f.get("FilingType") or "").upper() in {"P", "PTR"}
    ]
    logger.info("[house] {} total filings, {} PTRs for {}", len(filings), len(ptr_filings), year)

    new_rows = 0
    for filing in ptr_filings:
        name = _full_name(filing)
        if not name:
            continue
        member = ensure_placeholder_member(db, name, "house")
        doc_id = filing.get("DocID") or ""
        filing_date: date | None = parse_date(filing.get("FilingDate"))

        # We don't yet parse the transactions — just record a synthetic marker trade
        # per filing so the member's disclosure delay is visible in the dashboard.
        from poliwatch.ingestion._upsert import upsert_trade
        from poliwatch.models.trade import TradeType

        raw_url = PDF_URL.format(year=year, doc_id=doc_id) if doc_id else None
        upsert_trade(
            db,
            member_id=member.bioguide_id,
            ticker=None,
            asset_name=f"(House PTR filing {doc_id})",
            trade_type=TradeType.OTHER,
            trade_date=filing_date or date(year, 1, 1),
            disclosure_date=filing_date,
            disclosure_delay_days=None,
            amount_range=None,
            amount_min=None,
            amount_max=None,
            source=SOURCE,
            raw_url=raw_url,
        )
        new_rows += 1

    db.commit()
    mark_success(db, SOURCE, new_rows)
    return new_rows
