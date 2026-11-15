"""Market ex-dividend rule CANDIDATE for Korean equities, with the evidence that tests it.

Rule (T+2 settlement): the last cum-dividend session is the second session before
the LAST KRX SESSION ON OR BEFORE the record date; the ex-date is the session after
it, i.e. the session immediately before that last session.

    j = last session <= recordDate;  exDate = sessions[j - 1];  cum = sessions[j - 2]

For a record date that is itself a session this is the familiar "ex-date = one
session before the record date". It differs from
the first build of ``cohort.dividends.ex_date_candidate`` (which counted sessions STRICTLY before the
record date; corrected in this change) exactly when the record date is not a session -- e.g. every 12-31
record date, because KRX closes for the year-end holiday. Checked against publicly
reported year-end ex-dates (no price read):

* 2023: last session 12-28, 12-29 year-end holiday, ex-date 12-27, buy by 12-26
  (Kyunghyang 2023-12-14, khan.co.kr/article/202312141411001; Newsis 2023-12-26).
* 2022: last session 12-29, ex-date 12-28 (fnnews 2022-12-15,
  fnnews.com/news/202212151630345260).

The first build gave 12-28 (2023) and 12-29 (2022): one session late.
Neither rule is SEALED here; sealing a dated market rule from an official KRX/KSD
source is the Owner decision AGENTS v2.28 reserves. News reports are corroboration,
not the official rule text.
"""
from __future__ import annotations

from research.corporate_event_readiness_v1.cohort.dividends import MARKET_RULE_TIER, market_ex_date as _rule

TIER = MARKET_RULE_TIER
EVIDENCE = (
    {'year': 2023, 'recordDate': '2023-12-31', 'lastSession': '2023-12-28', 'reportedExDate': '2023-12-27',
     'source': 'https://www.khan.co.kr/article/202312141411001'},
    {'year': 2023, 'recordDate': '2023-12-31', 'lastSession': '2023-12-28', 'reportedExDate': '2023-12-27',
     'source': 'https://www.newsis.com/view/NISX20231226_0002570439'},
    {'year': 2022, 'recordDate': '2022-12-31', 'lastSession': '2022-12-29', 'reportedExDate': '2022-12-28',
     'source': 'https://www.fnnews.com/news/202212151630345260'},
)


def market_ex_date(record_date: str, sessions: list[str]) -> dict:
    """Thin view over ``cohort.dividends.market_ex_date`` (the single implementation)."""
    got = _rule(record_date, sessions)
    if got['exDateCandidate'] is None:
        return {'exDate': None, 'tier': got['exDateTier']}
    return {'lastSessionOnOrBeforeRecord': got['lastSessionOnOrBeforeRecord'],
            'cumDividendLastSession': got['cumDividendLastSession'], 'exDate': got['exDateCandidate'],
            'tier': TIER}
