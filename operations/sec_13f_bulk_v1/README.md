# SEC 13F offline bulk admission candidate

Status: INACTIVE / AUTHOR_VALIDATION_ONLY. Existing Pages requests returned HTTP 403 for seven managers. This does not establish the specific SEC IP-policy cause. Do not rotate proxies, spoof identities, bypass access controls, or scrape unverified vendors. Official source and documentation:
- https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets
- https://www.sec.gov/files/form_13f_readme.pdf
- https://www.sec.gov/about/developer-resources

As of 2026-11-27 the official catalog ends August 2026, so the September–November archive has not been observed. The existing individual EDGAR filing route remains more timely. The bulk reader uses original, independently obtained ZIP bytes offline; it does not download or assume a future URL exists. Example observed URL: https://www.sec.gov/files/datastandardsinnovation/data/form-13f-data-sets/01jun2026-31aug2026_form13f.zip. Web search text is not original XML/ZIP data.

Create a local JSON array of objects with path, exact official url, observed sha256 of downloaded bytes, and offset-aware retrievedAtUtc of the actual retrieval; retain the original archives and retrieval receipt separately. Run from repo root:

    python -m operations.sec_13f_bulk_v1.admission --manifest /tmp/manifest.json --report 2026-09-30 --out /tmp/13f-candidate.json

Supports only modern dollar-valued filings (post Jan 3 2023), contiguous filing-period coverage over target and previous report, CIK/accession joins, raw summary count and value reconciliation before aggregation, sequential amendments, no notice-as-zero, and explicit coverage cutoff. Any unsupported schema, ambiguity, or corrupt source blocks admission rather than inventing data. Actual ZIP schema/real records not yet exercised; strict parser may abstain on legitimate variants. Candidate-only output cannot be written into repository by CLI; it is not a production cache document. Hashes protect identity, not trust: review source provenance independently. The SEC warns its flat files may be incomplete and are not substitutes for complete filings.

Next operational gate: obtain the actual official ZIPs by a permitted route, independently verify source provenance and amendment chains against original filings, run candidate on current and previous quarters, compare all 7 managers with persisted cache, then review a separate authorized publication adapter to signal-history state/institutional_13f_cache.json (no regression, no same-quarter conflicting overwrite, no fabricated acceptance time, no live label). Preserve bootstrap and existing cache publishing contract. If GitHub can download official ZIPs normally, add bounded catalog-based acquisition; if blocked, support owner-supplied official archive through authenticated artifact transfer. No automatic production publication, no live retrieval or historical investment research executed here.

## Hardening after #381

Archive receipts must precede the decision clock and be later than the named window's final New York calendar day. This deliberately conservative admission rule may defer a legitimate early publication; never invent a receipt to pass it. Filing-date windows are not an acceptance-time census, and the SEC catalog's last-business-day cutoff can differ from a calendar label. Normal filing deadlines include weekend and Washington's Birthday adjustments. The cover's REPORTTYPE and summary's ISCONFIDENTIALOMITTED are required fields; combination reports or unknown/confidential omissions retain the disclosed total but withhold quarter-to-quarter quantity changes. Quantities are as disclosed, not proven purchases or sales, and are not split-adjusted. See SEC Form 13F Data Sets PDF sections 5.2, 5.5, 5.7 and SEC 13F FAQ. This remains a candidate-only offline route.
