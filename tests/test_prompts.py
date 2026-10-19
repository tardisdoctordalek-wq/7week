import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prompts import split_output, strip_citations, DRAFT_MARK, REVIEW_MARK  # noqa: E402


def test_strip_citations_and_split():
    raw = f"{DRAFT_MARK}\n1) 통증 : VAS 7→5 [근거: 통원 2026-10-02, p.3]\n{REVIEW_MARK}\n- ROM 미측정"
    draft, review = split_output(raw)
    assert strip_citations(draft) == "1) 통증 : VAS 7→5"
    assert review == "- ROM 미측정"
