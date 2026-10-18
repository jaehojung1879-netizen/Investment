"""KR adapters for the shared A0 engine, and a non-writing WP6 preview.

No prices after the signal, outcome readers, fitting, receipts or scheduling.
The existing US implementation and its default arguments remain the control.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import datetime as dt

import pandas as pd

from . import dart_derive as DD
from . import dart_fundamentals as DF
from . import kr_alpha_signal_v2 as H2
from . import kr_value_quality_catalyst as KQ
from . import prospective_receipt_core as CORE
from . import rp1_a0 as A
from . import winner_inflection as WI

COMPARATORS = ("C13_fundamentalAcceleration",)


class Filings:
    market = "KR"
    retention_reasons = ("AVAILABLE", "INCOMPLETE_TTM_CHAIN", "NON_POSITIVE_YOY_BASE",
                         "OPERATING_INCOME_NOT_STATED", "OPERATING_CASH_FLOW_NOT_STATED",
                         "OPERATING_INCOME_VALUE_UNRESOLVED", "OPERATING_CASH_FLOW_VALUE_UNRESOLVED")
    index = staticmethod(DD.index_filings)
    period_end = staticmethod(lambda key: DF.period_end(*key))

    @staticmethod
    def visible_day(row):
        public = row.get("availableFrom")
        if not public or not row.get("receiptNos") or {n[:8] for n in row["receiptNos"]} != {public.replace("-", "")}:
            return None
        return dt.date.fromisoformat(public)

    @staticmethod
    def current_key(index):
        return max(index, key=lambda k: (k[0], WI.STAGES["KR"].index(k[1]))) if index else None

    @staticmethod
    def values(index, key):
        used, failure = set(), []

        def ttm(k, account):
            deps = [k] if k[1] == DD.ANNUAL else [k, (k[0]-1, DD.ANNUAL), (k[0]-1, k[1])]
            used.update(deps)
            if any(d not in index for d in deps):
                failure.append("INCOMPLETE_TTM_CHAIN")
                return None
            if any(DF.period_end(*d) > index[d]["availableFrom"] for d in deps):
                failure.append("REPORT_PERIOD_AFTER_PUBLICATION")
                return None
            if not KQ._compatible(index, deps):
                failure.append("STATEMENT_BASIS_UNRESOLVED" if any(index[d].get("fsDiv") not in ("CFS","OFS") for d in deps)
                               else "STATEMENT_BASIS_CONFLICT")
                return None
            value = DD.trailing_twelve_months(index, *k, account)[0]
            if not A.finite(value):
                prefix = "OPERATING_INCOME" if account == "영업이익" else "OPERATING_CASH_FLOW"
                failure.append(prefix+("_NOT_STATED" if any(account not in index[d].get("accounts",{}) for d in deps)
                                       else "_VALUE_UNRESOLVED"))
                return None
            return float(value)
        values = (ttm(key, "영업이익"), ttm((key[0]-1, key[1]), "영업이익"), ttm(key, "영업활동현금흐름"))
        if all(d in index for d in used) and not KQ._compatible(index, sorted(used)):
            return None, None, None, ("STATEMENT_BASIS_UNRESOLVED" if any(index[d].get("fsDiv") not in ("CFS","OFS") for d in used)
                                     else "STATEMENT_BASIS_CONFLICT")
        priority = ("REPORT_PERIOD_AFTER_PUBLICATION", "STATEMENT_BASIS_UNRESOLVED", "STATEMENT_BASIS_CONFLICT", "INCOMPLETE_TTM_CHAIN",
                    "OPERATING_INCOME_NOT_STATED", "OPERATING_CASH_FLOW_NOT_STATED",
                    "OPERATING_INCOME_VALUE_UNRESOLVED", "OPERATING_CASH_FLOW_VALUE_UNRESOLVED")
        return (*values, next((r for r in priority if r in failure), "AVAILABLE"))

    @staticmethod
    def fields(index, key):
        # Same DART fields and FA delta/composite as C13. Never call its closed
        # discovery/evaluation modules. Incompatible TTM bases withhold controls.
        deps = [key] if key[1] == DD.ANNUAL else [key, (key[0]-1, DD.ANNUAL), (key[0]-1, key[1])]
        if not KQ._compatible(index, deps):
            return {}
        fields = DD.derive_fields(index, *key)[0]
        prior = (key[0]-1,key[1])
        prior_deps = [prior] if key[1]==DD.ANNUAL else [prior,(key[0]-2,DD.ANNUAL),(key[0]-2,key[1])]
        if not KQ._compatible(index, deps+prior_deps):
            fields.pop("earningsGrowth",None)
        return fields

    @classmethod
    def deltas(cls, index, key, ticker, public):
        previous = WI.previous_period(key,"KR")
        if previous not in index or index[previous].get("fsDiv")!=index[key].get("fsDiv"):
            return {}
        current = A.PIT.FundamentalRecord(ticker,f"{key[0]}-{key[1]}",public,cls.fields(index,key))
        old = A.PIT.FundamentalRecord(ticker,f"{previous[0]}-{previous[1]}",index[previous]["availableFrom"],cls.fields(index,previous))
        return A.FA.compute_deltas(current,old)


def eligibility(rows, day):
    """Original H2 eligibility including industry minimum; not H2 value ranking.

    Financials and unresolved identities never enter an eligible peer set.
    Keep all reasons for audit, use one ordered primary reason for accounting.
    """
    base = {}
    for row in rows:
        reasons = (["DEFINITIONALLY_EXCLUDED_FINANCIAL"] if row.get("sector") == "FINANCIALS" else [])
        if not row.get("issuerId"):
            reasons.append("IDENTITY_UNRESOLVED")
        reasons += H2._ineligibility(row, pd.Timestamp(day))
        base[row["ticker"]] = reasons
    groups = Counter(r.get("industry") for r in rows if not base[r["ticker"]])
    for row in rows:
        if not base[row["ticker"]] and groups[row["industry"]] < H2.MIN_INDUSTRY_MEMBERS:
            base[row["ticker"]].append("INDUSTRY_BELOW_MIN_MEMBERS")
    return base


def diagnostics(report):
    """Full-period formal gates; annual/recent diagnostics are NOT new gates."""
    groups = {"FULL_PERIOD": report["byDate"], "LATEST_52_WEEKS": report["byDate"][-52:]}
    for row in report["byDate"]:
        groups.setdefault(row["date"][:4], []).append(row)
    out = {}
    for name, days in groups.items():
        out[name] = {"dates": len(days), "firstDate": days[0]["date"] if days else None,
                     "lastDate": days[-1]["date"] if days else None, "hypotheses": {}}
        for h in A.HYPOTHESES:
            eligible = sum(d["eligible"] for d in days)
            measured = sum(d["hypotheses"][h]["measured"] for d in days)
            counts = [d["hypotheses"][h]["events"] for d in days]
            out[name]["hypotheses"][h] = {"eligible": eligible, "measured": measured,
                "missing": eligible-measured,
                "measurability": measured/eligible if eligible else None,
                "events": sum(n or 0 for n in counts) if measured else None, "datesUnmeasured": sum(n is None for n in counts),
                "datesWithAtLeastFiveSignals": sum(n is not None and n >= 5 for n in counts),
                "minKnownSignals": min((n for n in counts if n is not None), default=None),
                "medianKnownSignals": float(pd.Series([n for n in counts if n is not None]).median()) if measured else None}
    return out


def peer_diagnostics(observations):
    days = {}
    for row in observations:
        days.setdefault(row.key.signal_date, [])
        if row.investable is True:
            days[row.key.signal_date].append(row)
    result = []
    for day, rows in sorted(days.items()):
        cells = {o.key.sample_id:{c.name:c.value for c in o.cells} for o in rows}
        missing = [o for o in rows if cells[o.key.sample_id].get("price.relative126") is None or
                   cells[o.key.sample_id].get("risk.marketCap") is None]
        result.append({"date":day,"eligible":len(rows),
            "eligibleMissingPastWindow":sum(cells[o.key.sample_id].get("price.relative126") is None for o in rows),
            "eligibleMissingMarketCap":sum(cells[o.key.sample_id].get("risk.marketCap") is None for o in rows),
            "industries":len({o.industry_id for o in rows}),
            "industriesWithMissingPeer":len({o.industry_id for o in missing}),
            "h3Measured":sum(cells[o.key.sample_id].get("financial.A_H3") is not None for o in rows)})
    return result


def stratum_identities(observations):
    """Same A0 terciles, from the whole eligible date cross-section only."""
    days = {}
    for o in observations:
        if o.key.market != "KR":
            raise ValueError("KR_OBSERVATION_REQUIRED")
        if o.investable is True:
            days.setdefault(o.key.signal_date, []).append(o)
    output = {}
    for rows in days.values():
        cells = {o.key.sample_id: {c.name:c.value for c in o.cells} for o in rows}
        size = A.terciles({sid:c.get("risk.marketCap") for sid,c in cells.items()})
        movement = A.terciles({sid:c.get("price.relative126") for sid,c in cells.items()})
        for o in rows:
            sid = o.key.sample_id
            output[sid] = {}
            for h in A.HYPOTHESES:
                parts = (o.industry_id,size.get(sid)) + (() if h=="A-H2" else (movement.get(sid),))
                output[sid][h] = "|".join(str(x) for x in parts) if all(x is not None for x in parts) else "STRATUM_UNRESOLVED"
    return output


def receipt_preview(observation, *, merged_at_utc, spec_sha256, code_hashes, input_sha256, reasons, strata):
    """Always PREVIEW_ONLY; system clock, no writer, no authorization bypass.

    A historical observation can be represented, but fails the live timing
    window and is never relabelled as a prospective receipt.
    """
    if observation.key.market != "KR":
        raise ValueError("KR_OBSERVATION_REQUIRED")
    for sha in (spec_sha256, input_sha256, *code_hashes.values()):
        if not CORE.is_sha256(sha):
            raise ValueError("PREVIEW_HASH_REQUIRED")
    now = CORE.system_utc_now()
    blockers = ["A2_NOT_AUTHORIZED"]
    try:
        CORE.check_timing(signal_date=observation.key.signal_date, created_at_utc=now,
                          now_utc=now, merged_at_utc=merged_at_utc)
    except ValueError as exc:
        blockers.append(str(exc).split(":")[0])
    if observation.knowledge_policy != "OBSERVED_PROSPECTIVE":
        blockers.append("INPUTS_PUBLIC_RECONSTRUCTION_NOT_PROSPECTIVE_OBSERVATIONS")
    if observation.investable is not True:
        blockers.append(observation.eligibility_reason)
    cells = {c.name: c for c in observation.cells}
    body = {"mode": "PREVIEW_ONLY_NOT_A_RECEIPT", "evidenceClass": "NONE", "signalSession": observation.key.signal_date,
        "generatedAtUtc": now.isoformat(), "securityIdentity": observation.key.security_identity,
        "workbenchKey": asdict(observation.key), "sampleId": observation.key.sample_id,
        "legacyKeyMapping": {"date": observation.key.signal_date, "region": "KR", "ticker": observation.ticker,
                             "modelVersion": "rp1-kr-a2-preview-v1"},
        "states": {h: {"value": cells["financial."+h.replace("-", "_")].value,
                        "unknownReason": reasons.get(h) if cells["financial."+h.replace("-", "_")].value is None else None}
                   for h in A.HYPOTHESES},
        "availability": {c.name: {"availableAt": c.available_at, "observedAt": c.source.observed_at,
                                   "observationGap": c.source.observation_gap, "sourceSha256": c.source.sha256} for c in observation.cells},
        "stratumInputs": {"industry": observation.industry_id, "sizeBasis": "SIGNAL_DATE_MARKET_CAP",
                          "priorMovementBasis": "PAST_126_KR_SESSIONS_VS_069500.KS"},
        "stratumIdentity": {h:strata.get(h,"STRATUM_UNRESOLVED") for h in A.HYPOTHESES},
        "specSha256": spec_sha256, "codeHashes": dict(sorted(code_hashes.items())), "inputSha256": input_sha256,
        "blockers": blockers, "ledgerWrites": 0, "productionEffect": "NONE"}
    CORE.scan_for_outcome_keys(body)
    return {**body, "previewSha256": CORE.receipt_digest(body)}
