import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pii_check import MASK, mask_pii  # noqa: E402
from prompts import split_output, strip_citations, DRAFT_MARK, REVIEW_MARK  # noqa: E402


def masked(text):
    return mask_pii(text)[0]


def test_resident_number():
    assert "900101-1234567" not in masked("주민번호 900101-1234567 확인")
    assert "9001011234567" not in masked("번호 9001011234567")


def test_phone_and_email():
    out = masked("연락처 010-1234-5678, 02-123-4567, a.b@test.co.kr")
    assert "1234-5678" not in out and "123-4567" not in out and "@" not in out


def test_labeled_name_and_chart_number():
    out = masked("환자명: 홍길동\n차트번호: 12345")
    assert "홍길동" not in out and "12345" not in out
    assert out.count(MASK) == 2


def test_already_masked_name_kept():
    _, findings = mask_pii("성명: ○○○")
    assert findings == []


def test_vehicle_and_address():
    out = masked("차량 12가 3456, 주소 테헤란로 123")
    assert "3456" not in out and "테헤란로 123" not in out


def test_clinical_values_untouched():
    text = "2026-10-02 경추 굴곡 30도, VAS 7/10, Spurling test (+), 침 치료 1회"
    assert masked(text) == text


def test_strip_citations_and_split():
    raw = f"{DRAFT_MARK}\n1) 통증 : VAS 7→5 [근거: 2026-10-02, p.3]\n{REVIEW_MARK}\n- ROM 미측정"
    draft, review = split_output(raw)
    assert strip_citations(draft) == "1) 통증 : VAS 7→5"
    assert review == "- ROM 미측정"
