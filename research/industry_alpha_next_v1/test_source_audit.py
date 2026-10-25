"""Schema drift fixture with invented names, no source acquisition."""
import unittest

from research.industry_alpha_next_v1.source_audit import sector_schema_audit


class SchemaAuditTests(unittest.TestCase):
    def test_industry_labels_in_sector_column_cannot_pass_unnoticed(self):
        data = {"failures": [], "snapshots": [dict(date="2030-01-01", sourceCommit="synthetic",
                sectorColumn="Sector", rows={"SYN:A": {"sector": "Semiconductors"},
                "SYN:B": {"sector": None}}, membersWithoutRow=["SYN:C"], rawCsvSha256="a" * 64)]}
        result = sector_schema_audit(data)
        self.assertEqual(result["outsideTodayVocabularyRows"], 2)
        self.assertEqual(result["blankRows"], 1)
        self.assertEqual(result["snapshotsWithMemberRowGaps"], 1)
        self.assertEqual(data["snapshots"][0]["rows"]["SYN:A"]["sector"], "Semiconductors")


if __name__ == "__main__":
    unittest.main()
