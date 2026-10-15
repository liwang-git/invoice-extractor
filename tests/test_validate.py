import json
from pathlib import Path

import pytest

from extractor.validate import check_totals

CASES_DIR = Path(__file__).parent.parent / "evals" / "cases"
CASE_DIRS = sorted(CASES_DIR.iterdir())


# parametrize turns one test function into one test per eval case, so a
# failure report names the exact invoice that broke (e.g. [inv_010]).
@pytest.mark.parametrize("case_dir", CASE_DIRS, ids=lambda p: p.name)
def test_check_totals_matches_expected(case_dir):
    expected = json.loads((case_dir / "expected.json").read_text())
    assert check_totals(expected) == expected["review_reason"]
