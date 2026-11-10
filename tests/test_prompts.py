import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prompts import split_output, strip_citations, DRAFT_MARK, REVIEW_MARK  # noqa: E402


def test_strip_citations_and_split():
    raw = f"{DRAFT_MARK}\n1) 통증 : VAS 7→5 [근거: 통원 2026-10-02, p.3]\n{REVIEW_MARK}\n- ROM 미측정"
    draft, review = split_output(raw)
    assert strip_citations(draft) == "1) 통증 : VAS 7→5"
    assert review == "- ROM 미측정"


import prompts  # noqa: E402
from datetime import date  # noqa: E402

from prompts import TreatmentPlan, apply_fixed_answers, fixed_answers  # noqa: E402

PLAN = TreatmentPlan(date(2026, 9, 20))
LINE7 = "7) 필요한 치료의 종류·빈도·예상 기간 : " + fixed_answers(PLAN)[7]


def test_item7_replaced_single_line():
    draft = "6) 이유 : 잔존 [근거: p.1]\n7) 필요한 치료의 종류·빈도·예상 기간 : 주 3회 침 4주\n8) 검사 : 없음"
    assert apply_fixed_answers(draft, PLAN) == "6) 이유 : 잔존 [근거: p.1]\n" + LINE7 + "\n8) 검사 : 없음"


def test_item7_replaced_multiline_keeps_blank_line():
    draft = "6) 이유 : 잔존\n\n7) 필요한 치료 : [원장 기재 필요]\n- 침 치료\n- 추나\n\n8) 검사 : 없음"
    assert apply_fixed_answers(draft, PLAN) == "6) 이유 : 잔존\n\n" + LINE7 + "\n\n8) 검사 : 없음"


def test_item7_last_or_missing():
    assert apply_fixed_answers("7) 치료 : 미정", PLAN) == LINE7
    assert apply_fixed_answers("6) 이유 : 잔존\n8) 검사 : 없음", PLAN) == "6) 이유 : 잔존\n" + LINE7 + "\n8) 검사 : 없음"
    assert apply_fixed_answers("6) 이유 : 잔존", PLAN) == "6) 이유 : 잔존\n" + LINE7


def test_item17_not_confused_with_7():
    draft = "6) 이유 : VAS 7) 이후 악화\n7) 치료 : x\n8) 검사 : 없음"
    assert apply_fixed_answers(draft, PLAN).splitlines() == ["6) 이유 : VAS 7) 이후 악화", LINE7, "8) 검사 : 없음"]


def test_item7_sentence_matches_doctor_example():
    assert PLAN.sentence() == (
        "증상 조절 및 기능 회복을 위한 주 2~3회의 침, 약침 및 한방물리요법 등이 필요하며, "
        "사고일 기준 8주 경과일 2026.11.14 이후에도 약 4주간 2026.12.12까지의 "
        "추가적인 치료 및 경과 관찰이 필요할 것으로 판단됨."
    )


def test_item7_dates_and_custom_fields():
    assert TreatmentPlan(date(2026, 9, 20), 8).dates() == (date(2026, 11, 14), date(2027, 1, 9))
    # 월말·윤년 넘김: 2027-12-31 사고 → 8주 경과일 2028-02-24, +4주 2028-03-23
    assert TreatmentPlan(date(2027, 12, 31), 4).dates() == (date(2028, 2, 24), date(2028, 3, 23))
    custom = TreatmentPlan(date(2026, 9, 20), 8, "주 3회", "침 및 추나요법")
    assert "주 3회의 침 및 추나요법 등이" in custom.sentence() and "약 8주간 2027.01.09까지" in custom.sentence()
    draft = "6) 이유 : 잔존\n7) 치료 : x\n8) 검사 : 없음"
    assert custom.sentence() in apply_fixed_answers(draft, custom)
    assert custom.sentence() in prompts.build_system_prompt(prompts.MODE_FACTS, custom)


def test_mode_rules_differ():
    facts = prompts.build_system_prompt(prompts.MODE_FACTS, PLAN)
    prognosis = prompts.build_system_prompt(prompts.MODE_PROGNOSIS, PLAN)
    assert "예후나 기대 효과" in facts and "치료 지속 시 추가 호전이 기대됨" not in facts
    assert "추세 근거가 없는 예후" in prognosis and "기대 문장은 쓰지 않는다" in prognosis
    for text in (facts, prognosis):
        assert "종합 소견은 쓰지 않음" in text and "진료기록상 확인되지 않음" in text
