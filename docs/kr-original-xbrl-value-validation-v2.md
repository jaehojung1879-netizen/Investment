# Original DART XBRL fixed-sample validation v2

Single-rule follow-up to the closed
[v1](kr-original-xbrl-value-validation-v1.md) (merged in #169, verdict
**BLOCKED**, 60 AMBIGUOUS_SOURCE_FACT, run `36519798469`, artifact
`11012284532`). v1 files are never edited and a v1 rerun must still return
BLOCKED. This is not an Alpha experiment, an accounting repair or the Alpha-v5
input seal.

## Why v2 exists

All 60 v1 items stopped at one rule: `context entity scheme not independently
established as DART identity`. The served contexts use scheme
`http://dart.fss.or.kr/ifrs/CIK`, which v1 did not admit.

## Independent evidence (recorded before the protocol freeze)

Supplied by the requester; the authoring environment's egress proxy blocks
these hosts, so they were not re-fetched and are recorded as cited.

1. **XBRL 2.1 Specification** (XBRL International), §4.7.3.1: the identifier
   element's required `scheme` attribute holds the namespace URI of the
   identification scheme, and XBRL assumes no application can resolve that
   identifier or URI.
   <https://www.xbrl.org/Specification/xbrl-recommendation-2003-12-31.pdf>
2. **OpenDART developer guide** (FSS): `corp_code` is the disclosing company's
   8-digit corporation code (example `00126380`).
   <https://engopendart.fss.or.kr/guide/detail.do?apiGrpCd=DE002&apiId=AE00029>
3. **KPMG Korea XBRL seminar material** (2023-04-28): a context example shows
   `<identifier scheme="http://dart.fss.or.kr/ifrs/CIK">00126380</identifier>`.
   <https://assets.kpmg.com/content/dam/kpmg/kr/pdf/2023/kr-kpmg-xbrl-seminar-20230428.pdf>

Together: the URI is an entity identification scheme namespace (not
web-resolvable by requirement), and the value it carries in DART contexts is the
8-digit DART corporation code. That all 60 v1 files contained the URI motivated
v2 but is not used as evidence.

**Scope of the rule.** Exactly the string `http://dart.fss.or.kr/ifrs/CIK`, with
identifier text equal to the frozen `corpCode`. A different text is
METADATA_MISMATCH. No stockCode substitution under this scheme.

**Why not broader.** The evidence names one URI. A scheme URI is an opaque
namespace name, so wildcard/prefix or CIK-like matching would admit identifiers
no evidence covers. Other schemes behave exactly as in v1.

## Design

- Same 60 items, same sample SHA-256
  `590513ede1c8bd06d701f22f4b1aa01bcf8b004aa30b9410540865696e863e70`, same
  candidate SHA-256 `af642e7e…21dc3d1cc`. No new sampling or seed.
- The shared reader takes an explicit scheme option defaulting to the v1 rule.
  Only `pipeline/kr_xbrl_value_validation_v2.py` and its script enable the CIK
  scheme, under the frozen v2 protocol.
- Everything after the entity check still runs (period, basis, unit,
  decimals/precision, presentation, transforms, duplicates, exact Decimal). A
  matching raw amount alone is not a MATCH.
- If another systematic blocker appears, v2 stays BLOCKED; no further rule is
  widened inside v2.
- Classifications and PASS/FAIL/BLOCKED semantics are unchanged.
- One formal live run, after the freeze and green CI, via the existing
  `secrets.DART` with `contents: read` and `actions: read` only.
- `CANDIDATE_UNCONFIRMED` is promoted only on 60/60 MATCH, with no new
  production enum. Next task after PASS: KR repaired-input snapshot freeze +
  accounting semantic contract.
