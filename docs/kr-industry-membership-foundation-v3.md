# KR industry membership foundation v3 — KRX current state + official change events

Status: PROTOCOL FROZEN, no source acquired yet. v1/v2 (`DATA_FOUNDATION_INSUFFICIENT_V2`, 3.93% classified) are not modified or reinterpreted.

* Current-state anchor: the official KRX industry-classification dataset (Data Marketplace 업종분류 현황 or the equivalent official exchange table). The KRX OPEN API base-info service is not used unless live evidence shows a real economic-industry field (`SECT_TP_NM` is 소속부).
* Primary change events: KIND 업종변경 notices. Secondary only: DART disclosures and retained v1/v2 bytes, for identity breaks, mergers, spin-offs, terminal securities and unresolved KIND cases. No new broad DART campaign.
* A current anchor is `CURRENT_ONLY_CROSSCHECK` and is never admitted to a historical date.
* Backward reconstruction uses dated events that themselves state before and after labels. The oldest interval has no dated start and is `UNVERIFIED_START_NOT_PIT`; a broken chain leaves older dates UNKNOWN.
* Gates are inherited unchanged from the v2 criteria. The frozen request list and rules are in `research_specs/kr-industry-membership-foundation-v3/protocol.json` (sha256 sidecar).

No return, factor or Alpha outcome is read; no taxonomy or granularity is chosen from outcomes.
