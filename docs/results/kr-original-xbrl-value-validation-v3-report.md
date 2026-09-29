# Original XBRL source-value audit v3 — PASS (60/60 MATCH)

Follows the closed [v1](kr-original-xbrl-value-validation-v1-report.md) and
[v2](kr-original-xbrl-value-validation-v2-report.md) results (both BLOCKED, untouched)
and the [presentation diagnostic](kr-original-xbrl-presentation-evidence-diagnostic-v1-report.md).
Protocol frozen at `8456693de19edb6950f2587bd4b671182c045d0c`, SHA-256
`302fc108b9ed37053dc1e006c1079fa730dfff5aab907fe705f008485939fe84`. Same 60
frozen facts, sample SHA-256
`590513ede1c8bd06d701f22f4b1aa01bcf8b004aa30b9410540865696e863e70`, candidate
SHA-256 `af642e7e79e9ba59ac6ee14faf033f4d63887188bab6506845c082e21dc3d1cc`.

## Result

One formal live run: Actions run `36567349736` (head `c04230e5`), artifact
`11031774326` (zip SHA-256
`191980b45395582218a977f4d43a080caf5e3529bc43d28effa4a10c75c7b2b6`, report SHA-256
`522a9d1d621366927f90dd602e81b36ce9057406ae2e09e3fad47ceed42d82a1`). No retry. All
57 receipts served. Per-item fields are reproduced from the job log; the artifact
zip could not be downloaded from the authoring environment.

| Classification | Count |
|---|---:|
| MATCH | 60 |
| VALUE_MISMATCH | 0 |
| SEMANTIC_MISMATCH | 0 |
| METADATA_MISMATCH | 0 |
| AMBIGUOUS_SOURCE_FACT | 0 |
| SOURCE_UNAVAILABLE | 0 |
| INFRASTRUCTURE_ERROR | 0 |

**Overall verdict: PASS.** For every item: one source fact at the recorded
pointer; IFRS-namespace concept (`http://xbrl.iasb.org/taxonomy/2010-04-30/ifrs`)
with the frozen local name; entity scheme `http://dart.fss.or.kr/ifrs/CIK` with
identifier equal to the frozen `corpCode`; period, CFS/OFS basis and KRW unit as
frozen; unitRef and decimals as recorded (48 at 0, 8 at -6, 4 at -3); exact Decimal
comparison at the declared accuracy. The source value also equalled the stored
candidate exactly in 60/60.

## What the PASS does and does not show

- **MATCH does not rest on presentation.** Presentation corroboration was 0 of 60,
  as v2 and PR #171 found. v3 replaced that gate with the explicit concept-identity
  rule preregistered before the run. The ZIPs give no independent proof that the
  filing displays each fact in its named statement, and the IFRS taxonomy files were
  not fetched.
- **Scope of the evidence.** 60 stored original-XBRL facts from fiscal 2015
  Q1/H1/Q3, a balanced deterministic (not random) sample. The descriptive
  two-sided 95% upper mismatch bound is 5.96% under a binomial assumption. It is not
  a population guarantee and says nothing about later years or the canonical-v2
  records.
- **Design disclosure.** The v3 rules were written after v1/v2 and PR #171 had
  exposed structure and, descriptively, that raw text equalled the candidate. They
  came from source structure, not per-item values, and no item was replaced or
  reclassified.

## Confidence

The fixed-sample evidence now supports promoting the original-XBRL candidate values
beyond `CANDIDATE_UNCONFIRMED`, with the limits above. No production enum is
invented, no candidate was repaired, no v5 input is sealed, and no Alpha workflow or
outcome data was used. The next separate task is **KR repaired-input snapshot freeze
+ accounting semantic contract**.
