import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prompts import split_output, strip_citations, DRAFT_MARK, REVIEW_MARK  # noqa: E402


def test_strip_citations_and_split():
    raw = f"{DRAFT_MARK}\n1) 통증 : VAS 7→5 [근거: 통원 2026-10-02, p.3]\n{REVIEW_MARK}\n- ROM 미측정"
    draft, review = split_output(raw)
    assert strip_citations(draft) == "1) 통증 : VAS 7→5"
    assert review == "- ROM 미측정"


from prompts import FIXED_ANSWERS, apply_fixed_answers  # noqa: E402

LINE7 = "7) 필요한 치료의 종류·빈도·예상 기간 : " + FIXED_ANSWERS[7]


def test_item7_replaced_single_line():
    draft = "6) 이유 : 잔존 [근거: p.1]\n7) 필요한 치료의 종류·빈도·예상 기간 : 주 3회 침 4주\n8) 검사 : 없음"
    assert apply_fixed_answers(draft) == "6) 이유 : 잔존 [근거: p.1]\n" + LINE7 + "\n8) 검사 : 없음"


def test_item7_replaced_multiline_keeps_blank_line():
    draft = "6) 이유 : 잔존\n\n7) 필요한 치료 : [원장 기재 필요]\n- 침 치료\n- 추나\n\n8) 검사 : 없음"
    assert apply_fixed_answers(draft) == "6) 이유 : 잔존\n\n" + LINE7 + "\n\n8) 검사 : 없음"


def test_item7_last_or_missing():
    assert apply_fixed_answers("7) 치료 : 미정") == LINE7
    assert apply_fixed_answers("6) 이유 : 잔존\n8) 검사 : 없음") == "6) 이유 : 잔존\n" + LINE7 + "\n8) 검사 : 없음"
    assert apply_fixed_answers("6) 이유 : 잔존") == "6) 이유 : 잔존\n" + LINE7


def test_item17_not_confused_with_7():
    draft = "6) 이유 : VAS 7) 이후 악화\n7) 치료 : x\n8) 검사 : 없음"
    assert apply_fixed_answers(draft).splitlines() == ["6) 이유 : VAS 7) 이후 악화", LINE7, "8) 검사 : 없음"]
