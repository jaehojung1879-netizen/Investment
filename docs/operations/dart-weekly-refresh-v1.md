# DART weekly operational refresh v1

Owner conditional approval for this operational refresh is recorded in #292
comment 7141424919.
The existing workflow runs a second cron at 19:17 UTC Tuesday (04:17 KST
Wednesday). The original 03:40 UTC daily KR/US jobs and the manual raw routes
retain their trigger. No additional writer, same concurrency group. Schedule
runs on main only and requires both collector repairs present before calls.
600 statement calls / 120 minutes per weekly slice, current and previous fiscal
years (previous first Jan–Apr, current first May–Dec). The budget is a ceiling;
no new paid source. The sealed universe/legacy input is still the exact
4ea107ed0cde289f0a049a65ff13d2441a786710 commit. The scheduled branch writes
only kr-raw and kr-canonical-v2, not the merged candidate or original XBRL.
Git push remains fast-forward with existing retry/rebase logic. The audit uses
only the sealed backward measurement inputs. No historical return or formal
execution, no changes to registered specs or past receipts.

Historical workflow provenance: the original fundamentals blob is recovered
from main 4f4497bcc9e7f9369bf5529225585ad39b0d7725 and verified against its Git
blob identity. The current operational workflow must equal the exact permitted
transformations. The existing WP2 full tree hash is then recomputed using that
original blob, together with the already admitted Pages/Tests originals; all
other files must match the frozen tree. No expected hash is updated. Independent
review must verify the narrow compatibility addition; all native CI must pass.
The original v2 spec's manual-only statement is the registration-time fact,
not an edit to its scientific method.

Merging this change into main enables the schedule. Before merging, confirm
that #377 and #379 passed exact-head Tests and independent review and that this
workflow passed the same checks against the merged main. Verify the first raw
and canonical commit, Q3 served count, newest availableFrom and next v2 receipt
freshness in the stored data. The weekly run uses the sealed universe and the
registered receipt rules. GitHub cron can be delayed and concurrency can
replace a pending run.
