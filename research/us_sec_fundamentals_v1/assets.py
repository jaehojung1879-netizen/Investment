"""Attach SEC total assets to the same dated filing for research."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pipeline import finnhub_derive, finnhub_fundamentals, us_cash_profitability
from pipeline.us_total_assets_source import ACCESSION_RE, normalize_accession, normalize_cik

PAYLOAD = Path(__file__).with_name("assets.jsonl")
SHA256 = "413b925b33afa709adf5b3e7c459a08d21de4ef4dacf0be9eed405798c8e2000"
NEW_YORK = ZoneInfo("America/New_York")
SOURCES = {"companyfacts", "fsds", "filing"}


@dataclass(frozen=True)
class AssetFact:
    period_end: date
    filed: date
    accepted: datetime
    usd: int | float
    source: str

    @property
    def accepted_local(self) -> datetime:
        return self.accepted.astimezone(NEW_YORK)


def _asset_index(raw: bytes) -> dict[tuple[str, str], AssetFact]:
    """Read [CIK, accession, period end, filed, accepted, USD, source] rows."""
    index = {}
    for line in raw.splitlines():
        cik, accession, period_end, filed, accepted, usd, source = json.loads(line)
        if normalize_cik(cik) != cik or not ACCESSION_RE.fullmatch(accession) or normalize_accession(accession) != accession:
            raise ValueError("Invalid SEC filing identity")
        fact = AssetFact(date.fromisoformat(period_end), date.fromisoformat(filed), datetime.fromisoformat(accepted), usd, source)
        if (
            fact.accepted.tzinfo is None or fact.period_end > fact.filed or fact.period_end > fact.accepted_local.date()
            or type(usd) not in (int, float) or not math.isfinite(usd) or usd <= 0 or source not in SOURCES
        ):
            raise ValueError(f"Invalid SEC asset fact: {accession}")
        key = cik, accession
        if key in index:
            raise ValueError(f"Duplicate SEC asset fact: {key}")
        index[key] = fact
    return index


def load_assets() -> dict[tuple[str, str], AssetFact]:
    raw = PAYLOAD.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise ValueError("SEC asset payload hash mismatch")
    return _asset_index(raw)


def with_sec_assets(record: dict, assets: dict[tuple[str, str], AssetFact], as_of: date) -> dict:
    """Supply a missing account only when both sources are visible by the signal date."""
    cik = normalize_cik(record.get("cik"))
    accession = str(record.get("accession") or "")
    if not cik or not ACCESSION_RE.fullmatch(accession):
        return record
    canonical_accession = normalize_accession(accession)
    fact = assets.get((cik, canonical_accession))
    if (
        fact is None or record.get("periodEnd") != fact.period_end.isoformat()
        or str(record.get("availableFrom") or "")[:10] != fact.filed.isoformat()
        or max(fact.filed, fact.accepted_local.date()) >= as_of
    ):
        return record
    try:
        vendor_accepted = datetime.fromisoformat(str(record.get("acceptedDate") or ""))
    except ValueError:
        return record
    if vendor_accepted.tzinfo:
        vendor_accepted = vendor_accepted.astimezone(NEW_YORK)
    if vendor_accepted.date() >= as_of:
        return record
    statements = record.get("statements") or {}
    balance = statements.get("bs") or []
    if any(finnhub_fundamentals.strip_namespace(item.get("concept")) in finnhub_derive.ASSETS for item in balance):
        return record
    asset = {"concept": "us-gaap_Assets", "unit": "USD", "value": fact.usd}
    return {
        **record,
        "statements": {**statements, "bs": [*balance, asset]},
        "secAssetSource": {"accession": canonical_accession, "accepted": fact.accepted.isoformat(), "source": fact.source},
    }


def features_as_of(records: list[dict], as_of: str, assets: dict[tuple[str, str], AssetFact], *, cik: str) -> dict:
    """Run the repository's current cash-profitability calculation with the SEC overlay."""
    issuer = normalize_cik(cik)
    if issuer is None:
        raise ValueError("A dated issuer CIK is required")
    day = date.fromisoformat(as_of)
    inputs = [with_sec_assets(record, assets, day) for record in records
              if normalize_cik(record.get("cik")) == issuer]
    return us_cash_profitability.features_as_of(inputs, as_of)
