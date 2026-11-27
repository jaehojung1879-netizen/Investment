"""Verify the narrow, source-only input census against pinned repository objects."""

import argparse
import csv
import io
import json
import subprocess
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULT = HERE / "results" / "prior-source-audit.json"
MAIN = "3150c70017432e3b73321fbda47ebea226bf8d2b"
S1 = "f223c1c7d8c841500ea99b2caadeaa72f7a0cce7"
S2 = "46f181f4c75c4fe0e273fcb288feaebbea24dd12"
S3 = "17a9514e06cefd5176cc2a6c05453f003f4e9c17"
NETWORK = "research/economic_network_event_first_v1/data"
INSTITUTIONAL = "research/market_structure_discovery_s2/results"
DISCLOSURE = "research/market_structure_discovery_s3"


def read_commit(ref, path):
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=HERE, text=True)


def derive():
    fda = json.loads(read_commit(S1, f"{NETWORK}/fda_metrics.json"))
    issuer_rows = list(csv.DictReader(io.StringIO(read_commit(S1, f"{NETWORK}/fda_issuer_exposure.csv"))))
    sector_counts = dict(sorted((k, v["events"]) for k, v in fda["domains"].items()))
    product_linked = [r for r in issuer_rows if r["linked_510k_90d_before"]]
    same_name = [r for r in product_linked if r["linked_510k_same_name_90d_before"]]
    source = json.loads(read_commit(S2, f"{INSTITUTIONAL}/ledger-summary.json"))
    economics = [json.loads(r) for r in read_commit(S3, f"{DISCLOSURE}/ECONOMIC-EVENTS.jsonl").splitlines()]
    review = json.loads(read_commit(S3, f"{DISCLOSURE}/independent_evaluation_v1/EVALUATION-SPEC.json"))
    vintages = json.loads(read_commit(S3, f"{DISCLOSURE}/independent_evaluation_v1/SOURCE-EVIDENCE.json"))
    bls = list(csv.DictReader(io.StringIO(read_commit(S1, f"{NETWORK}/bls_event_first_91.csv"))))
    lineage = json.loads((HERE / "results" / "pr-lineage.json").read_text())
    if [item["pr"] for item in lineage] != list(range(343, 370)):
        raise ValueError("The full requested PR range must be represented")
    return {
        "refs": {"main": MAIN, "s1_with_event_first_followup": S1, "s2_pr384": S2, "s3": S3},
        "closed_and_open_pr_metadata_records": len(lineage),
        "economic_network": {
            "openfda_product_records_with_keys": fda["distinct_enforcement_product_keys"],
            "fda_distinct_event_ids_by_domain": sector_counts,
            "device_class_i_ids": fda["domains"]["device"]["class_i_events"],
            "device_class_i_with_listing_date": fda["class_i_has_device_post"],
            "bls_candidate_episode_rows": len(bls),
            "class_i_pre_event_issuer_and_product_clusters": len({r["cluster_90d"] for r in product_linked}),
            "class_i_same_legal_name_clusters": len({r["cluster_90d"] for r in same_name}),
            "largest_linked_issuer_cluster_count": Counter(cik for cik, _ in {
                (r["cik"], r["cluster_90d"]) for r in product_linked
            }).most_common(1)[0][1],
        },
        "institutional_constraints": {
            "sp500_announcement_dates": source["sp500"]["distinctAnnouncementDates"],
            "sp500_effective_dates": source["sp500"]["distinctEffectiveDates"],
            "kospi200_regular_review_dates_measured": source["kospi200"]["distinctRegularReviewDates"],
            "kosdaq150_regular_review_dates_measured": source["kosdaq150"]["distinctRegularReviewDates"],
            "kofia_forced_sale_spike_sessions": source["kofia"]["forcedSaleSpikeSessions"],
            "kofia_episode_groups": source["kofia"]["forcedSaleIndependentEpisodes"],
        },
        "public_information": {
            "economic_rows": len(economics),
            "entity_ids": len({r["entityId"] for r in economics}),
            "rows_with_first_publication_unverified": sum(
                r["disclosureNoveltyStatus"] == "FIRST_PUBLICATION_UNVERIFIED" for r in economics
            ),
            "independent_evaluation_status": review["status"],
            "independent_evaluation_target_issuers": review["cohort"]["issuerClustersTarget"],
            "expert_forecast_vintages": vintages["targetVintageCount"],
            "expert_unique_target_keys": vintages["uniqueExpertTargetKeys"],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = json.dumps(derive(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if RESULT.read_text() != result:
            raise SystemExit(f"Result does not reproduce: {RESULT}")
        print(f"Verified {RESULT.name}")
    else:
        RESULT.write_text(result)


if __name__ == "__main__":
    main()
