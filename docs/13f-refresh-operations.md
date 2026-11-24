# SEC 13F disclosure refresh (dashboard only)

- The existing Pages schedule checks SEC twice per weekday and once per weekend day.
  A successful deployment publishes a separate rolling cache to
  `signal-history:state/institutional_13f_cache.json` if at least one manager
  was retrieved live. The next build reads this file from its already-fetched
  signal-history ref and merges it with the immutable bootstrap cache on main.
  No strategy, model state, historical ledger or pinned seed is rewritten.
- No live retrieval means no publication. The dashboard reports the source
  failure separately from the official historical disclosures. The due
  quarter follows the normal SEC deadline (45 calendar days, weekend and
  Washington's Birthday adjustment; due day itself is not called overdue).
  An overdue or missing disclosure may mean a manager no longer files, not
  necessarily a source outage.
- Source is SEC EDGAR only. Requests declare the operator and accept compressed
  responses. HTTP 403/429 are not retried aggressively. If SEC refuses the
  runner's requests, neither the new cache nor the site can manufacture the
  missing quarter; a later successful scheduled fetch is required.
- Amendments: a restatement replaces the preceding table; a NEW HOLDINGS
  amendment is appended to the preceding valid table. Missing or unknown
  chains fail closed. Nonconsecutive quarters are not labeled a quarterly
  holdings comparison.
- Operator checks: the Pages build log prints the SEC error class and HTTP
  status for each failed manager; the post-deploy step warns on zero live
  or due-quarter gaps. A successful Pages deployment is not proof of SEC
  access. Verify the next run and the published cache's actual report dates.
- Local source check: `python -m pipeline.institutional_13f` returns nonzero
  on zero live results and prints coverage. It updates the local official
  cache only from actual SEC responses. Do not commit a refreshed bootstrap
  cache to main: the historical bootstrap hash is pinned in the UI.
- SEC bulk Form 13F ZIPs are published following February/May/August/November;
  the 2026 September–November package was not yet available as of 2026-11-25.
  No unverified third-party scraping or rate-limit bypass is introduced.
