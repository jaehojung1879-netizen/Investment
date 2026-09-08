"""KRW policy-rate proxy, sourced from the BOK's dated decision history.

This is a disclosed cash/risk-free proxy, not a claim to an investable deposit
or a government-bill total-return index. The rate is effective the following
calendar day, avoiding use before the decision was announced.
"""
import json
from pathlib import Path
from urllib.request import Request, urlopen
from io import StringIO

import pandas as pd

SOURCE = "https://www.bok.or.kr/portal/singl/baseRate/list.do?dataSeCd=01&menuNo=200643"
FALLBACK = Path(__file__).resolve().parent.parent / "data" / "bok-policy-rates.json"


def fetch_rates(through):
    try:
        with urlopen(Request(SOURCE, headers={"User-Agent":"Investment historical research"}), timeout=30) as response:
            html = response.read().decode("utf-8")
        tables = pd.read_html(StringIO(html))
        events = []
        for table in tables:
            if table.shape[1] < 3:
                continue
            for values in table.itertuples(index=False, name=None):
                year, day, rate = str(values[0]), str(values[1]), values[2]
                if not year[:4].isdigit() or "월" not in day:
                    continue
                stamp = pd.Timestamp(f"{year[:4]}-{day.replace('월','-').replace('일','').replace(' ','')}")
                effective = (stamp + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
                if effective <= through:
                    events.append({"date":effective, "annualRatePct":float(rate)})
        if not events or min(r["date"] for r in events) > "2013-01-01":
            raise ValueError("BOK history missing the replay origin")
        return {"source":SOURCE, "basis":"BOK_POLICY_RATE_PROXY", "verifiedThrough":through,
                "events":sorted(events,key=lambda r:r["date"])}
    except Exception as exc:
        result = json.loads(FALLBACK.read_text())
        print(f"BOK rate history: committed observed snapshot through {result['verifiedThrough']} ({type(exc).__name__})")
        return result
