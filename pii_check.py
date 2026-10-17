"""진료기록 텍스트에 남아 있는 개인식별정보를 찾아 가린다.

정규식 기반이라 놓치거나(미탐) 과하게 잡을(오탐) 수 있다.
전송 전 원장님이 마스킹 결과를 직접 확인하는 것을 전제로 한다.
"""

import re
from dataclasses import dataclass

MASK = "[가림]"

# (종류, 패턴, 가릴 그룹 번호) — 그룹 0이면 매치 전체를 가린다.
_PATTERNS = [
    ("주민등록번호", re.compile(r"(?<!\d)\d{6}\s*-\s*[1-8]\d{6}(?!\d)"), 0),
    ("주민등록번호 의심(하이픈 없음)", re.compile(r"(?<!\d)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[1-8]\d{6}(?!\d)"), 0),
    ("휴대전화번호", re.compile(r"(?<!\d)01[016789]\s*[-.]?\s*\d{3,4}\s*[-.]?\s*\d{4}(?!\d)"), 0),
    ("전화번호", re.compile(r"(?<!\d)0(?:2|[3-6][1-5]|70)\s*[-.)]\s*\d{3,4}\s*[-.]\s*\d{4}(?!\d)"), 0),
    ("이메일", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), 0),
    ("차량번호", re.compile(r"(?<![\d가-힣])\d{2,3}\s?[가-힣]\s?\d{4}(?!\d)"), 0),
    ("이름(항목명 뒤)", re.compile(r"(?:성명|환자명|환자\s*성명|이름|보호자|피보험자|운전자)\s*[:：]?\s*([가-힣]{2,4})(?![가-힣])"), 1),
    ("차트·등록번호", re.compile(r"(?:차트\s*번호|등록\s*번호|병록\s*번호|환자\s*번호|접수\s*번호|사고\s*번호)\s*[:：]?\s*([A-Za-z0-9-]{4,})"), 1),
    ("도로명 주소", re.compile(r"[가-힣0-9]+(?:로|길)\s*\d+(?:-\d+)?(?:\s*,?\s*\d+\s*동)?(?:\s*\d+\s*호)?"), 0),
]

# 이미 가려진 값(○○○, ***, XXX 등)은 이름으로 보지 않는다.
_ALREADY_MASKED = re.compile(r"^[○●*xX□■]+$")


@dataclass
class Finding:
    kind: str
    text: str
    start: int
    end: int


def find_pii(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for kind, pattern, group in _PATTERNS:
        for m in pattern.finditer(text):
            value = m.group(group)
            if not value or _ALREADY_MASKED.match(value):
                continue
            findings.append(Finding(kind, value, m.start(group), m.end(group)))
    return _drop_overlaps(findings)


def _drop_overlaps(findings: list[Finding]) -> list[Finding]:
    # 겹치는 탐지는 먼저 시작하고 더 긴 것을 남긴다.
    findings.sort(key=lambda f: (f.start, -(f.end - f.start)))
    kept: list[Finding] = []
    for f in findings:
        if kept and f.start < kept[-1].end:
            continue
        kept.append(f)
    return kept


def mask_pii(text: str) -> tuple[str, list[Finding]]:
    findings = find_pii(text)
    out = text
    for f in reversed(findings):
        out = out[: f.start] + MASK + out[f.end :]
    return out, findings
