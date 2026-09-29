# Original DART XBRL fixed-sample validation v3

Completes the source-value audit of the same frozen 60 facts (sample SHA-256
`590513ede1c8bd06d701f22f4b1aa01bcf8b004aa30b9410540865696e863e70`, candidate
SHA-256 `af642e7e…21dc3d1cc`). v1 (entity scheme) and v2 (presentation gate) are
closed BLOCKED; PR #171 diagnosed why v2's gate cannot be satisfied.

## What changes, and only this

1. **Presentation membership is no longer a mandatory gate.** PR #171 showed, on 12
   of the frozen 60, that the DART packages carry no role definitions (roles point
   to an external DART taxonomy), reference standard concepts through external
   DART-hosted hrefs, and contain no presentation loc at all for Assets/Liabilities
   (6/6). The evidence is still computed and stored per item as corroboration; it
   never changes a classification.
2. **Explicit concept identity replaces it.** The source fact's concept must be the
   IFRS-taxonomy concept named by the frozen family (ProfitLoss,
   CashFlowsFromUsedInOperatingActivities, Assets, Liabilities), identified by
   expanded QName (IFRS namespace URI read from the instance itself, plus local
   name). The candidate's statement code must fit the family. A fact in any other
   namespace (extension concept) is never assumed equivalent to a standard concept;
   v3 admits no lineage evidence, so it is AMBIGUOUS_SOURCE_FACT.

Everything else is inherited: exact instance pointer, duplicate consistency,
period, CFS/OFS basis, KRW unit, unitRef/decimals provenance, transformation
refusal, Decimal comparison at declared accuracy, the v2 rule that scheme
`http://dart.fss.or.kr/ifrs/CIK` must carry the frozen `corpCode` (no stockCode
fallback), classifications and verdict semantics.

## Limits stated up front

Concept identity plus context, basis, period, unit, decimals and amount identify
the fact. They do not independently prove the filing displays it in the named
statement, and the IFRS taxonomy files are not fetched. If all 60 MATCH, that is
fixed-sample evidence with this limit, nothing more.

## Discipline

- A mismatch is reported with evidence and never repaired or reclassified here.
- A new systematic blocker leaves v3 BLOCKED; a further change needs a new version.
- One formal live run after the freeze and green CI, via `secrets.DART`.
- The rules were designed after the v1/v2 logs and PR #171 exposed structure and,
  descriptively, that raw source text equalled the candidate amount for the 60
  items. The rules come from structure, not from any per-item value, and no item is
  replaced, but the design is not blind to that observation. This is disclosed
  rather than hidden.
- No candidate repair, v5 seal or Alpha execution; no historical outcome is read.
