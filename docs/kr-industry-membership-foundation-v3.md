# KR industry membership foundation v3 — KRX current state + official change events

Status: **`DATA_FOUNDATION_INSUFFICIENT_V3`** (see Result). Earlier text below records the state before the scoped document stage. v1/v2 (`DATA_FOUNDATION_INSUFFICIENT_V2`, 3.93% classified) are not modified or reinterpreted.

* Current-state anchor: the official KRX industry-classification dataset (Data Marketplace 업종분류 현황 or the equivalent official exchange table). The KRX OPEN API base-info service is not used unless live evidence shows a real economic-industry field (`SECT_TP_NM` is 소속부).
* Primary change events: KIND 업종변경 notices. Secondary only: DART disclosures and retained v1/v2 bytes, for identity breaks, mergers, spin-offs, terminal securities and unresolved KIND cases. No new broad DART campaign.
* A current anchor is `CURRENT_ONLY_CROSSCHECK` and is never admitted to a historical date.
* Backward reconstruction uses dated events that themselves state before and after labels. The oldest interval has no dated start and is `UNVERIFIED_START_NOT_PIT`; a broken chain leaves older dates UNKNOWN.
* Gates are inherited unchanged from the v2 criteria. The frozen request list and rules are in `research_specs/kr-industry-membership-foundation-v3/protocol.json` (sha256 sidecar).

No return, factor or Alpha outcome is read; no taxonomy or granularity is chosen from outcomes.

## Observed (outcome-free)

State at the end of the broad discovery stage (superseded by the Result section): v3 admitted no classification.

| Source | Result |
|---|---|
| KIND listed-company table (current) | Served once (run 37170219625): 2,802 rows, every row with an 업종 label, 158 distinct labels. 232 of the 260 ever-Top120 securities appear (28 absent). `CURRENT_ONLY_CROSSCHECK`: not admitted to any historical date. Raw bytes retained under `data/.../probe/`. |
| KRX Data Marketplace 업종분류 현황 | Page returned an error page and the OTP returned `LOGOUT` (login required in that run). Unavailable anonymously. |
| Same four requests re-run (run 37170262633) | All four answered Akamai `Access Denied` 403. Access from Actions is intermittent by runner/edge, so the first run's bytes are the evidence. |
| KIND 업종변경 listing | Revisions: rev2 and rev3 received KIND `페이지 오류` pages, which the first parser misread as empty (fixed and pinned by test); rev4, with the complete search form, listed **968 notices (968 unique receipts)** in 67 requests (2013: 26 … 2026: 30), all titles in the 업종변경 family, 745 companies. |

The frozen document-stage rule is "fetch notice documents only if listed hits <= 400, otherwise stop and report". 968 > 400, so the broad population was not fetched; the scoped revision below replaced that stage. Titles alone assign nothing. A narrower document stage (for example only notices matching the Top120 universe, about 62 notices on exact company-name scoping, which is scoping and not identity) would be a new pre-registered revision, and the KIND document-viewer endpoints are unconfirmed.

Reconstruction code is tested on synthetic events only: the oldest interval is `UNVERIFIED_START_NOT_PIT`, broken chains stop. Nothing real has been reconstructed.

## Scoped document stage (rev5/rev6) and Result

* Candidate list frozen **before any notice body was fetched** (`research_specs/.../top120-notice-candidates.json`, sha256 `ea79816a…`): the 968 listed notices joined by exact whitespace-normalised company name to any name recorded for an ever-Top120 security gives **81 candidate notices** (not 62: the repository records historical names too). Name matching is candidate discovery only.
* Mechanics, disclosed: rev5 requested the KIND viewer page for all 81 (retained); it names no document URL, so rev6 (same candidate list) POSTs the viewer's own `searchContents` form for the `docNo` the viewer page lists and fetches the document path that response names. Result: **81 of 81 served, 162 further requests, 0 unresolved**; no candidate was added, dropped or substituted.
* Identity: the notice documents state the company name but no stock code. KIND's viewer header for the same receipt states `<company> (<stock code>)`; that retained header is the identity source and the code must equal exactly one candidate security. Disclosed interpretation of the frozen identity rule, made when the format became visible, before any extraction.
* Extraction (parser `kr-industry-v3-notice-parser-2`): only labelled facts. Two explicit formats: the structured 업종변경 form (변경 전/후 업종 and code, 변경일, 변경사유) and the 기타시장안내 free text, where the labelled 소분류 name is the label. **80 of 81 admitted** as change events; 1 (카카오, 20130430000262) states no effective date and stays unresolved.
* Strong consistency check: for all 62 securities with events, the last disclosed after-label equals the current KIND anchor label, and no between-event chain mismatched (0 conflicts).

| Result (610 signal dates × 120 = 73,200 name-dates; UNKNOWN in every denominator) | |
|---|---|
| Current anchor | 232 of 260 ever-Top120 securities; 28 absent. Table 2,802 rows, 2,759 distinct codes, duplicate rows identical |
| Verified change events | 80 (securities with 0 / 1 / 2+ events: 198 / 47 / 15) |
| Reconstructed classified name-dates | 68,807 (93.999%); UNKNOWN 4,393 |
| By status | stable no-change inference 54,173; verified event intervals 7,076; current anchor 7,558; UNKNOWN 4,391; terminated 2; retained-DART fallback 0 |
| Signal-date coverage min / median / max | 90.00% / 94.17% / 97.50% |
| Annual coverage | 91.88% (2018) to 97.48% (2026) |
| Terminal securities | 0 / 2,345 name-dates (the 28 absent securities have no historical KIND evidence; no fallback exists) |
| Conflicts | 0 intervals |
| Groups | 78 distinct raw KIND labels; group size min / median / max 1 / 1 / 21; every date has ≥3 groups of ≥5 names |
| Gates (numeric, inherited unchanged from v2) | signal coverage PASS, annual coverage PASS, minimum 3 sufficient groups PASS, **terminal coverage FAIL (0% vs 90%)**, **fraction in sufficient groups FAIL** |

**Decision: `DATA_FOUNDATION_INSUFFICIENT_V3`**, because two frozen gates fail: terminal-security coverage and the share of classified names sitting in groups of at least five names (raw KIND labels are fine-grained; no coarser grouping was chosen, since choosing granularity here would be a post-observation tuning).

Limits stated plainly: 54,173 of the 68,807 classified name-dates rest on the inference that a security with a current anchor and no candidate notice never changed 업종 since 2013. That inference depends on a listing that searched only the keyword 업종변경 and on name-based discovery, which can miss a notice filed under a name absent from the universe record. Only 1,798 event-interval name-dates were demonstrably public (notice date before the signal date). This is a reconstruction; nothing here claims PIT_EXACT. KSIC editions are unverified and not required.
