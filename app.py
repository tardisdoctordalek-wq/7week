"""자동차보험 경상환자 8주 초과 치료 필요성 소견서 작성 보조 앱.

실행: streamlit run app.py   (Windows는 실행.bat 더블클릭)
"""

import io
import os
from pathlib import Path

import streamlit as st
from pypdf import PdfReader

import llm
import prompts
from pii_check import mask_pii

APP_DIR = Path(__file__).parent
KRW_PER_USD = 1400  # 비용 표시용 환율 (추정치)
MIN_CHARS_PER_PAGE = 30  # 이보다 글자가 적으면 스캔(이미지) PDF로 본다


def load_saved_key(provider: dict) -> str:
    for name in provider["env"]:
        if os.environ.get(name):
            return os.environ[name]
    key_file = APP_DIR / provider["key_file"]
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    return ""


def extract_pdf(name: str, data: bytes) -> tuple[str, list[int]]:
    """쪽 표시를 붙인 텍스트와, 글자가 거의 없는(스캔 의심) 쪽 번호 목록을 돌려준다."""
    reader = PdfReader(io.BytesIO(data))
    chunks, empty_pages = [], []
    for i, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").strip()
        if len(text) < MIN_CHARS_PER_PAGE:
            empty_pages.append(i)
        chunks.append(f"=== {name} p.{i} ===\n{text}")
    return "\n\n".join(chunks), empty_pages


st.set_page_config(page_title="8주 초과 치료 소견서 보조", page_icon="📝", layout="wide")
st.title("📝 8주 초과 치료 필요성 소견서 작성 보조")
st.caption("진료기록에 근거한 초안을 만듭니다. 최종 판단·수정·서명은 원장님이 하셔야 합니다.")

# ---------- 사이드바: 설정 ----------
with st.sidebar:
    st.header("설정")
    model_label = st.selectbox("AI 모델", list(llm.MODELS))
    model = llm.MODELS[model_label]
    provider = llm.PROVIDERS[model["provider"]]
    saved_key = load_saved_key(provider)
    api_key = st.text_input(f"{provider['name']} API 키", value=saved_key, type="password", key=f"key_{model['provider']}")
    if api_key and api_key != saved_key and st.button("이 PC에 키 저장"):
        (APP_DIR / provider["key_file"]).write_text(api_key.strip(), encoding="utf-8")
        st.success(f"{provider['key_file']}에 저장했습니다.")
    if model["provider"] == "google":
        st.warning(
            "Google 무료 키(결제 미등록)로 쓰면, 구글 약관상 입력 자료가 제품 개선에 사용되고 "
            "사람 검토자가 읽을 수 있습니다. 결제를 등록한 유료 사용은 해당되지 않습니다."
        )
    st.markdown("---")
    st.markdown("**서식**")
    st.text(prompts.TEMPLATE)

# ---------- 1. 업로드 ----------
st.subheader("1. 진료기록 PDF 업로드")
files = st.file_uploader(
    "비식별화한 진단서·진료기록부 PDF (여러 개 가능)", type=["pdf"], accept_multiple_files=True
)
if not files:
    st.info("PDF를 올려주세요. 원본 PDF는 이 PC 밖으로 나가지 않고, 추출한 글자만 AI로 전송됩니다.")
    st.stop()

texts, scanned = [], {}
for f in files:
    try:
        text, empty_pages = extract_pdf(f.name, f.getvalue())
    except Exception as e:  # 손상·암호 PDF 등
        st.error(f"{f.name}: PDF를 읽지 못했습니다 ({e})")
        st.stop()
    texts.append(text)
    if empty_pages:
        scanned[f.name] = empty_pages

if scanned:
    detail = ", ".join(f"{name} p.{','.join(map(str, pages))}" for name, pages in scanned.items())
    st.warning(
        f"글자를 추출하지 못한 쪽이 있습니다: {detail}\n\n"
        "스캔(사진) PDF로 보입니다. 이 쪽들은 개인정보 검사를 할 수 없어 AI에 보내지 않습니다. "
        "EMR에서 PDF로 직접 출력한 파일을 사용해 주세요."
    )

raw_text = "\n\n".join(texts)

# ---------- 2. 개인정보 점검 ----------
st.subheader("2. 개인정보 점검")
masked_text, findings = mask_pii(raw_text)
if findings:
    st.warning(f"개인정보로 의심되는 {len(findings)}곳을 [가림]으로 바꿨습니다. 아래 목록과 전송될 내용을 확인해 주세요.")
    st.table({"종류": [f.kind for f in findings], "원래 값": [f.text for f in findings]})
else:
    st.success("자동 점검에서 개인정보 패턴이 발견되지 않았습니다.")
st.caption("자동 점검은 정해진 패턴만 찾습니다. 이름·주소가 다른 형태로 남아 있을 수 있으니 직접 확인해 주세요.")

with st.expander("AI에 전송될 내용 보기 (마스킹 적용 후)", expanded=bool(findings)):
    st.text_area("전송 내용", masked_text, height=400, disabled=True, label_visibility="collapsed")

confirmed = st.checkbox("전송될 내용을 확인했고, 환자를 특정할 수 있는 정보가 없습니다.")

# ---------- 3. 작성 ----------
st.subheader("3. 소견서 초안 작성")
memo = st.text_area(
    "원장님 메모 (선택)",
    placeholder="기록에 없지만 반영할 내용. 예) 향후 4주간 주 3회 침·추나 치료 계획",
    height=80,
)

if st.button("초안 작성", type="primary", disabled=not (confirmed and api_key)):
    st.session_state.pop("result", None)
    placeholder = st.empty()
    streamed = []

    def show(chunk: str) -> None:
        streamed.append(chunk)
        placeholder.text("".join(streamed))

    try:
        res = llm.generate(
            model, api_key.strip(), prompts.SYSTEM_PROMPT, prompts.build_user_message(masked_text, memo), show
        )
    except llm.LLMError as e:
        placeholder.empty()
        st.error(str(e))
        st.stop()
    placeholder.empty()

    output = res.text
    draft, review = prompts.split_output(output)
    st.session_state["result"] = {
        "draft": draft,
        "review": review,
        "truncated": res.truncated,
        "input_tokens": res.input_tokens,
        "output_tokens": res.output_tokens,
        "cost": llm.cost_usd(model, res.input_tokens, res.output_tokens),
        "model": model_label,
        "provider": model["provider"],
    }

result = st.session_state.get("result")
if result:
    if result["truncated"]:
        st.warning("출력이 길이 제한에 걸려 중간에 끊겼습니다. 결과 끝부분을 확인해 주세요.")

    tab_review, tab_submit, tab_check = st.tabs(["검토용 (근거 표시)", "제출용 (근거 제거)", "보강·확인 필요 사항"])
    with tab_review:
        st.caption("각 문장 끝의 [근거: ...]를 진료기록과 대조해 확인해 주세요.")
        st.text_area("검토용", result["draft"], height=500, label_visibility="collapsed")
    with tab_submit:
        submit_text = prompts.strip_citations(result["draft"])
        st.text_area("제출용", submit_text, height=500, label_visibility="collapsed")
        st.download_button("제출용 텍스트 저장 (.txt)", submit_text, file_name="소견서_초안.txt")
    with tab_check:
        st.markdown(result["review"] or "검토사항이 출력되지 않았습니다.")

    st.caption(
        f"{result['model']} · 입력 {result['input_tokens']:,} 토큰 · 출력 {result['output_tokens']:,} 토큰 "
        f"(AI 사고과정 포함) · 이번 비용 약 ${result['cost']:.4f} ≈ {result['cost'] * KRW_PER_USD:,.0f}원 "
        f"(환율 {KRW_PER_USD:,}원 가정)"
        + (" · Google 무료 키라면 실제 청구액은 0원" if result["provider"] == "google" else "")
    )
