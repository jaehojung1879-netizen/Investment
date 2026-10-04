# KR industry membership foundation v3 — KRX current state + official change events

Status: PROTOCOL FROZEN, no source acquired yet. v1/v2 (`DATA_FOUNDATION_INSUFFICIENT_V2`, 3.93% classified) are not modified or reinterpreted.

* Current-state anchor: the official KRX industry-classification dataset (Data Marketplace 업종분류 현황 or the equivalent official exchange table). The KRX OPEN API base-info service is not used unless live evidence shows a real economic-industry field (`SECT_TP_NM` is 소속부).
* Primary change events: KIND 업종변경 notices. Secondary only: DART disclosures and retained v1/v2 bytes, for identity breaks, mergers, spin-offs, terminal securities and unresolved KIND cases. No new broad DART campaign.
* A current anchor is `CURRENT_ONLY_CROSSCHECK` and is never admitted to a historical date.
* Backward reconstruction uses dated events that themselves state before and after labels. The oldest interval has no dated start and is `UNVERIFIED_START_NOT_PIT`; a broken chain leaves older dates UNKNOWN.
* Gates are inherited unchanged from the v2 criteria. The frozen request list and rules are in `research_specs/kr-industry-membership-foundation-v3/protocol.json` (sha256 sidecar).

No return, factor or Alpha outcome is read; no taxonomy or granularity is chosen from outcomes.

## Observed (outcome-free)

Status now: **`DATA_FOUNDATION_INSUFFICIENT`** — v3 admits no point-in-time classification; v1/v2 are unchanged.

| Source | Result |
|---|---|
| KIND listed-company table (current) | Served once (run 37170219625): 2,802 rows, every row with an 업종 label, 158 distinct labels. 232 of the 260 ever-Top120 securities appear (28 absent). `CURRENT_ONLY_CROSSCHECK`: not admitted to any historical date. Raw bytes retained under `data/.../probe/`. |
| KRX Data Marketplace 업종분류 현황 | Page returned an error page and the OTP returned `LOGOUT` (login required in that run). Unavailable anonymously. |
| Same four requests re-run (run 37170262633) | All four answered Akamai `Access Denied` 403. Access from Actions is intermittent by runner/edge, so the first run's bytes are the evidence. |
| KIND 업종변경 listing | Revisions: rev2 and rev3 received KIND `페이지 오류` pages, which the first parser misread as empty (fixed and pinned by test); rev4, with the complete search form, listed **968 notices (968 unique receipts)** in 67 requests (2013: 26 … 2026: 30), all titles in the 업종변경 family, 745 companies. |

The frozen document-stage rule is "fetch notice documents only if listed hits <= 400, otherwise stop and report". 968 > 400, so no document was fetched and no before/after label exists. Titles alone assign nothing. A narrower document stage (for example only notices matching the Top120 universe, about 62 notices on exact company-name scoping, which is scoping and not identity) would be a new pre-registered revision, and the KIND document-viewer endpoints are unconfirmed.

Reconstruction code is tested on synthetic events only: the oldest interval is `UNVERIFIED_START_NOT_PIT`, broken chains stop. Nothing real has been reconstructed.
