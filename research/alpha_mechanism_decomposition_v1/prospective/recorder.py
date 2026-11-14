"""kr-four-book-prospective-record-v1 — the weekly receipt for four KR books (spec.json), PREPARED and NOT AUTHORIZED.

Nothing here invents a signal or a storage format.
  * Book rules CALL the frozen adaptive-cocktail-v1 sleeve function (`cocktail.sleeve_book`, vendored byte-identical) and this study's
    `analyze.industry_book`, so B1 and B2 are the exact books alpha-mechanism-decomposition-v1 measured; B3 is the same S2 call restricted to the
    B2 industries.
  * Storage, digest, outcome-key scan, timing window and the outcome join are `pipeline.prospective_receipt_core` (the format every KR study receipt
    uses). A held name without terminal consideration makes that book's outcome UNRESOLVED, never zero.

THREE PATHWAYS THAT NEVER MEET.
  LIVE            build_live_receipt — refuses while REGISTERED_AUTHORIZATION is None (it is). Time from the writer's clock only.
  SYNTHETIC       build_synthetic_receipt — tests only; an explicit test clock; labelled SYNTHETIC_FIXTURE.
  REPLAY_PREVIEW  build_preview_receipt — a past signal date the pinned inputs reach, to show what the first receipt WILL contain. Labelled
                  NOT_PROSPECTIVE_EVIDENCE; it can never enter a live ledger (validate_live refuses it) and never counts as an observation.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = STUDY.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pipeline import prospective_receipt_core as CORE  # noqa: E402


def _load(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


C = _load("amd_cocktail", STUDY / "vendor/adaptive_cocktail_v1/cocktail.py")
M = _load("amd_mechanism", STUDY / "mechanism.py")
SPEC_PATH = HERE / "spec.json"
SPEC = json.loads(SPEC_PATH.read_text())
STUDY_ID = SPEC["studyId"]
ETF = C.ETF
BOOKS = ("B0_069500_ONLY", "B1_S2_ORIGINAL", "B2_H01_CAP_INDUSTRY_BASKET", "B3_H01_INDUSTRIES_S2_SELECTION")
LIVE, SYNTHETIC, PREVIEW = "LIVE", "SYNTHETIC_FIXTURE", "REPLAY_PREVIEW_NOT_PROSPECTIVE_EVIDENCE"
REQUIRED_COLUMNS = ("ticker", "industry", "tradableAtSignal", "isPreferredShare", "E04_tradabilityGuard20", "E07_suspensionStaleRisk",
                    "E03_capacityMedianTradedValue60", "B08_valueBusinessConfirmation", "b08Confirmed", "b08State", "H01_industryRelMom126",
                    "A09_industryRelativeMomentum126", "_mcap")
# Registered by a later reviewed change once spec.json is merged and a post-2026-09-14 input loader exists. None: no live receipt can be built.
REGISTERED_AUTHORIZATION = None


def spec_sha256():
    return hashlib.sha256(SPEC_PATH.read_bytes()).hexdigest()


def code_identity():
    files = [HERE / "recorder.py", STUDY / "mechanism.py", STUDY / "analyze.py", STUDY / "vendor/adaptive_cocktail_v1/cocktail.py",
             ROOT / "pipeline/prospective_receipt_core.py"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


# --------------------------------------------------------------------------- #
# Book rules (frozen in spec.json)
# --------------------------------------------------------------------------- #
def industry_book(g, base):
    """Same as analyze.industry_book (each stock slot spread over its PIT cap-weighted quality-eligible industry basket)."""
    out = {}
    for a, w in base.items():
        if a in (ETF, C.CASH):
            out[a] = out.get(a, 0.0) + w
            continue
        ind = g.loc[g["ticker"] == a, "industry"].iloc[0]
        bw = {t: v for t, v in M.industry_basket(g, ind).items() if t not in C.WITHHELD} or {a: 1.0}
        s = sum(bw.values())
        for t, v in bw.items():
            out[t] = out.get(t, 0.0) + w * v / s
    return out


def _rank(ind_rank, industry):
    v = ind_rank.get(industry, np.nan) if isinstance(industry, str) else np.nan
    return None if pd.isna(v) else int(v)


def quality_failures(row):
    """Every guard of the frozen quality mask that this row fails, in the mask's own order."""
    out = []
    if not bool(row["tradableAtSignal"]):
        out.append("NOT_TRADABLE_AT_SIGNAL")
    if row["isPreferredShare"] is True or row["isPreferredShare"] == 1:
        out.append("PREFERRED_SHARE")
    if not (row["E04_tradabilityGuard20"] >= 20):
        out.append("FEWER_THAN_20_POSITIVE_VOLUME_SESSIONS")
    if not ((row["E07_suspensionStaleRisk"] if pd.notna(row["E07_suspensionStaleRisk"]) else 1) <= 0):
        out.append("SUSPENSION_OR_STALE_QUOTE_RISK")
    if not (row["E03_capacityMedianTradedValue60"] >= 5e9):
        out.append("MEDIAN_TRADED_VALUE_BELOW_5BN_KRW")
    return out


def decide(g):
    """All four books for one signal date's cross-section `g` (Phase B matrix rows + `_q`, `_mcap`). Pure: same rows, same books."""
    missing = [c for c in REQUIRED_COLUMNS if c not in g.columns]
    if missing:
        raise ValueError("MISSING_COLUMNS: " + ",".join(missing))
    g = g.reset_index(drop=True).copy()
    g["_q"] = C.quality_mask(g).to_numpy()
    if any(bool(not quality_failures(r)) != bool(q) for (_, r), q in zip(g.iterrows(), g["_q"])):
        raise AssertionError("QUALITY_REASONS_DISAGREE_WITH_THE_FROZEN_MASK")
    s1_w, s1_picks, _ = C.sleeve_book("S1_INDUSTRY_MOMENTUM", g)
    s2_w, s2_picks, s2_would = C.sleeve_book("S2_VALUE_CONFIRMED", g)
    industries = sorted({g.loc[g["ticker"] == t, "industry"].iloc[0] for t in s1_picks})
    s3_score = g["B08_valueBusinessConfirmation"].where((g["b08Confirmed"] == 1) & g["industry"].isin(industries))
    s3_w, s3_picks, s3_would = C.sleeve_book("S2_VALUE_CONFIRMED", g, score=s3_score)
    books = {"B0_069500_ONLY": {ETF: 1.0}, "B1_S2_ORIGINAL": s2_w, "B2_H01_CAP_INDUSTRY_BASKET": industry_book(g, s1_w),
             "B3_H01_INDUSTRIES_S2_SELECTION": s3_w}
    ind_rank = g.groupby("industry")["H01_industryRelMom126"].first().rank(ascending=False, method="min")
    out = {}
    for b, w in books.items():
        w = {t: float(v) for t, v in sorted(w.items()) if v > 1e-12}
        if abs(sum(w.values()) - 1.0) > 1e-9:
            raise AssertionError("BOOK_DOES_NOT_SUM_TO_ONE: " + b)
        out[b] = {"weights": w, "stockNames": len([t for t in w if t != ETF]), "fallbackWeight": w.get(ETF, 0.0),
                  "state": "FALLBACK_ONLY_069500" if set(w) == {ETF} else "HOLDS_STOCKS"}
    out["B1_S2_ORIGINAL"]["selection"] = _s2_selection(g, s2_picks, None, ind_rank)
    out["B1_S2_ORIGINAL"]["withheldWouldHavePicked"] = s2_would
    out["B3_H01_INDUSTRIES_S2_SELECTION"]["selection"] = _s2_selection(g, s3_picks, industries, ind_rank)
    out["B3_H01_INDUSTRIES_S2_SELECTION"]["withheldWouldHavePicked"] = s3_would
    out["B2_H01_CAP_INDUSTRY_BASKET"]["selection"] = {
        "s1Picks": [{"ticker": t, "industry": g.loc[g["ticker"] == t, "industry"].iloc[0],
                     "industryH01Rank": _rank(ind_rank, g.loc[g["ticker"] == t, "industry"].iloc[0])} for t in s1_picks],
        "industries": industries,
        "basketMembers": {ind: sorted(t for t in M.industry_basket(g, ind) if t not in C.WITHHELD) for ind in industries}}
    out["B0_069500_ONLY"]["selection"] = {"rule": "069500.KS 100%"}
    return out


def _s2_selection(g, picks, industries, ind_rank):
    """Why each name is in or out of an S2-rule book: the first failing gate, or its rank if it passed every gate."""
    score = g["B08_valueBusinessConfirmation"].where(g["b08Confirmed"] == 1)
    if industries is not None:
        score = score.where(g["industry"].isin(industries))
    ranked = g.assign(_s=score)[g["_q"] & score.notna() & ~g["ticker"].isin(C.WITHHELD)].sort_values(["_s", "ticker"], ascending=[False, True])
    rank = {t: i + 1 for i, t in enumerate(ranked["ticker"])}
    sel, excl = [], {}
    for _, r in g.sort_values("ticker").iterrows():
        t = r["ticker"]
        base = {"ticker": t, "industry": r["industry"] if isinstance(r["industry"], str) else None,
                "b08State": r["b08State"] if isinstance(r["b08State"], str) else None,
                "valuePercentileWithinIndustry": None if pd.isna(r["B08_valueBusinessConfirmation"]) else round(float(r["B08_valueBusinessConfirmation"]), 4),
                "industryH01Rank": _rank(ind_rank, r["industry"])}
        if t in picks:
            sel.append({**base, "rank": rank[t], "weight": 0.2})
            continue
        q = quality_failures(r)
        if q:
            reason = "QUALITY:" + "+".join(q)
        elif t in C.WITHHELD:
            reason = "WITHHELD_UNRESOLVED_CORPORATE_ACTION_BASIS"
        elif pd.isna(r["B08_valueBusinessConfirmation"]):
            reason = "S2_" + (r["b08State"] if isinstance(r["b08State"], str) else "UNMEASURED")
        elif r["b08Confirmed"] != 1:
            reason = "NOT_CONFIRMED:" + (r["b08State"] if isinstance(r["b08State"], str) else "UNMEASURED")
        elif industries is not None and r["industry"] not in industries:
            reason = "OUTSIDE_H01_INDUSTRIES"
        else:
            reason = "OUTRANKED:rank_%d" % rank[t]
        excl.setdefault(reason.split(":")[0], []).append({**base, "reason": reason})
    sel.sort(key=lambda x: x["rank"])
    return {"selected": sel, "eligibleRanked": len(rank), "excludedCounts": {k: len(v) for k, v in sorted(excl.items())},
            "nextOutranked": sorted(excl.get("OUTRANKED", []), key=lambda x: int(x["reason"].split("_")[-1]))[:5],
            "excluded": {k: v for k, v in sorted(excl.items())}}


# --------------------------------------------------------------------------- #
# Receipts
# --------------------------------------------------------------------------- #
def _receipt(pathway, signal_date, execution_date, g, created_at_utc, data_identity):
    books = decide(g)
    r = {"schemaVersion": 1, "studyId": STUDY_ID, "pathway": pathway, "specSha256": spec_sha256(), "codeIdentity": code_identity(),
         "signalDate": str(pd.Timestamp(signal_date).date()), "executionDate": str(pd.Timestamp(execution_date).date()),
         "createdAtUtc": CORE.utc(created_at_utc).isoformat(), "dataSnapshotIdentity": dict(data_identity),
         "universeRows": int(len(g)), "qualityEligible": int(C.quality_mask(g).sum()), "books": books,
         "costsAssumed": SPEC["costs"], "benchmark": ETF, "researchOnly": True, "productionEffect": "NONE",
         "evidenceClass": {LIVE: CORE.EVIDENCE_CLASS, SYNTHETIC: "SYNTHETIC_FIXTURE", PREVIEW: "NOT_PROSPECTIVE_EVIDENCE"}[pathway]}
    CORE.scan_for_outcome_keys(r)
    r["receiptSha256"] = CORE.receipt_digest(r)
    return r


def build_live_receipt(*, g, signal_date, data_identity):
    auth = REGISTERED_AUTHORIZATION
    if auth is None:
        raise ValueError("KR_FOUR_BOOK_RECORD_NOT_AUTHORIZED: spec.json is prepared, not authorized; no live receipt can be built")
    now = CORE.system_utc_now()
    execution = CORE.check_timing(signal_date=signal_date, created_at_utc=now, now_utc=now, merged_at_utc=auth["mergedAtUtc"])
    if auth["specSha256"] != spec_sha256():
        raise ValueError("SPEC_CHANGED_SINCE_AUTHORIZATION")
    return _receipt(LIVE, signal_date, execution, g, now, data_identity)


def build_synthetic_receipt(*, g, signal_date, test_clock_utc, data_identity):
    return _receipt(SYNTHETIC, signal_date, CORE.next_kr_session(pd.Timestamp(signal_date)), g, test_clock_utc, data_identity)


def build_preview_receipt(*, g, signal_date, execution_date, data_identity, clock_utc=None):
    """Past signal date reachable with the pinned inputs. Shows the content of a first receipt; it is not one."""
    return _receipt(PREVIEW, signal_date, execution_date, g, clock_utc or CORE.system_utc_now(), data_identity)


def validate(receipt, *, pathway):
    if receipt.get("pathway") != pathway:
        raise ValueError("PATHWAY_MISMATCH")
    if receipt.get("studyId") != STUDY_ID:
        raise ValueError("STUDY_MISMATCH")
    if CORE.receipt_digest(receipt) != receipt.get("receiptSha256"):
        raise ValueError("RECEIPT_DIGEST_MISMATCH")
    CORE.scan_for_outcome_keys({k: v for k, v in receipt.items() if k != "receiptSha256"})
    for b in BOOKS:
        w = receipt["books"][b]["weights"]
        if abs(sum(w.values()) - 1.0) > 1e-9 or len([t for t in w if t != ETF]) > (10 ** 6 if b == "B2_H01_CAP_INDUSTRY_BASKET" else 5):
            raise ValueError("BOOK_INVALID: " + b)


def append_live(path, receipt):
    return CORE.append(path, receipt, validate=lambda r: validate(r, pathway=LIVE), key_fields=("studyId", "signalDate"))


def append_synthetic(path, receipt):
    return CORE.append(path, receipt, validate=lambda r: validate(r, pathway=SYNTHETIC), key_fields=("studyId", "signalDate"))


def book_outcome(receipt, book, *, horizon, name_outcomes, now_utc, pathway):
    """Separate outcome record for one book, via prospective_receipt_core. 069500.KS must be in `name_outcomes` with excessReturn 0."""
    rec = CORE.build_outcome_record(receipt, validate=lambda r: validate(r, pathway=pathway), horizon=horizon, name_outcomes=name_outcomes,
                                    now_utc=now_utc, weights_field=("books", book, "weights"))
    rec["book"] = book
    return rec
