# KR industry membership foundation v4 — terminal completion and outcome-blind coarse taxonomy

Decision: **`DATA_FOUNDATION_INSUFFICIENT_V4`**. v1/v2/v3 are not modified; the v3 reconstruction for the 232 anchored securities is reused byte-for-byte (the builder refuses to run if the v3 audit changes). No return, factor or Alpha outcome was read, no taxonomy was chosen from outcomes, no DART collection was run and no sealed study was rerun.

## Preregistered before any new evidence or structural evaluation (commit fea9e780)
`research_specs/kr-industry-membership-foundation-v4/`: `protocol.json` (exact 28 absent securities = 22 terminal + 6 preferred shares, source priority, preferred-share identity rule, taxonomy selection rule with a 35% single-group dominance limit, inherited v2 numeric gates, UNKNOWN semantics) and `crosswalk.json` (all 82 whitespace-normalised raw KIND labels, 83 raw strings, mapped on economic meaning to 14 groups; successive KSIC-edition renames map to the same group).

## The 28 absent securities: 4 resolved, 24 unresolved
* **Preferred shares (6):** frozen rule needs BOTH a current-anchored stem code AND a recorded name equal to the common's KIND name plus a preferred suffix. 삼성전자우, LG생활건강우, LG화학우 and 아모레퍼시픽우 satisfy it and take their common stock's reconstructed intervals over their own Top120 dates (949 name-dates, status `PREFERRED_SHARE_OF_ANCHORED_COMMON`). 현대차우 and 현대차2우B fail the name condition (recorded `현대차…` versus KIND `현대자동차`); the rule was not relaxed after seeing this, so they stay UNKNOWN.
* **Terminal common stocks (22): 0 resolved.** None has a KIND/KRX record of its own that was reachable, no verified KIND notice, and no observation admitted by the unchanged v2 template from retained DART bytes. Retained terminal-action evidence supplies termination types only (share exchange / merger / share transfer / unresolved) and is never used for an industry; no industry is carried from a successor across those events. The single frozen probe of the official KIND delisted-company register (1 request, status 200, 83 KB, retained) shows only a search form (시장구분, 회사명, 기간); no industry field was observed (result columns were not observed).

## Taxonomy
* Official hierarchy: not usable. The structured notices carry six-digit codes and the free-text notices carry large/middle/small codes, but no label appears in both forms, so the code-prefix semantics cannot be proven (frozen requirement ≥5 agreeing overlaps), and only 38 of 82 raw labels have any retained official code. Both official candidates fail the "every raw label maps" rule.
* Economic crosswalk (frozen): 14 groups, every raw label mapped, 0 taxonomy-UNKNOWN name-dates, largest group 22.3% of classified name-dates (limit 35%), 6 to 12 groups of at least five names on every date (median 10).
* But on 398 of 610 dates less than 90% of classified names sit in groups of at least five (minimum 78.8%). Per the frozen selection rule no taxonomy is selected, and groups were not split, merged or tuned afterwards.

## Result (610 dates × 120 = 73,200 name-dates, UNKNOWN in every denominator)
| Metric | Value |
|---|---|
| Classified / UNKNOWN name-dates | 69,756 (95.295%) / 3,444 (v3: 68,807 / 4,393) |
| Signal-date coverage min / median / max | 91.67% / 95.83% / 98.33% |
| Annual coverage | 92.77% (2018) to 98.31% (2026) |
| Terminal-security name-date coverage | 0 / 2,345 |
| Raw industry labels in the research dates / coarse groups | 78 / 14 |
| Group size (coarse groups, per date) min / median / max | 1 / 6 / 34 |
| Conflicts / identity breaks (terminal set) | 0 / 22 |

Gates (inherited numeric gates plus the frozen taxonomy checks): signal coverage PASS, annual coverage PASS, at least 3 sufficient groups per date PASS, taxonomy mapping complete PASS, taxonomy dominance PASS, **terminal coverage FAIL (0% vs 90%)**, **fraction of classified names in groups of at least five FAIL (398 dates below 90%)**.

Remaining blockers: official historical industry information for the 22 delisted/merged securities was not reachable from the free sources probed, and the fine granularity of the 82 raw labels leaves too many names outside groups of five at a 14-group economic resolution. Closing either needs new official evidence or a new preregistered taxonomy, not a change to this one.
