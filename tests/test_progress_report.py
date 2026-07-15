import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


import progress_report  # noqa: E402


class TestProgressReport(unittest.TestCase):
    def test_claim_count_requires_numeric_claim_heading(self) -> None:
        text = """\
## CLM-XXXX: template
## CLM-0001: first
## CLM-0002
### CLM-0003: wrong level
## CLM-123: wrong width
## CLM-0004suffix
"""
        self.assertEqual(progress_report.count_claim_headings(text), 2)

    def test_glossary_count_requires_numeric_id_field(self) -> None:
        text = """\
- Id: TERM-XXXX
- Id: TERM-0001
  - Id: TERM-0002
- Id: TERM-123
- Related: TERM-0003
"""
        self.assertEqual(progress_report.count_glossary_id_fields(text), 2)


if __name__ == "__main__":
    unittest.main()
