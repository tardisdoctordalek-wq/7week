"""자동차보험 경상환자 8주 초과 치료 필요성 소견서 작성 보조 앱.

실행: streamlit run app.py   (Windows는 실행.bat 더블클릭)
"""

import io
import os
from pathlib import Path

import anthropic
import streamlit as st
from pypdf import PdfReader

import prompts
from pii_check import mask_pii

APP_DIR = Path(__file__).parent
KEY_FILE = APP_DIR / "api_key.txt"
KRW_PER_USD = 1400  # 비용 표시용 환율 (추정치)

# 100만 토큰당 USD. Haiku 5.5는 입력이 10만 토큰을 넘으면 비싼 단가가 적용된다.
MODELS = {
    "Haiku 5.5 (저렴)": {"id": "claude-haiku-5-5", "in": 0.10, "out": 0.50, "in_long": 0.50, "out_long": 2.50},
    "Sonnet 5.5 (중간)": {"id": "claude-sonnet-5-5", "in": 2.00, "out": 10.00},
    "Opus 5.5 (고품질)": {"id": "claude-opus-5-5", "in": 4.00, "out": 20.00},
}

MIN_CHARS_PER_PAGE = 30  # 이보다 글자가 적으면 스캔(이미지) PDF로 본다


def load_saved_key() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    if KEY_FILE.exists():
        return KEY_FILE.read_text(encoding="utf-8").strip()
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


def cost_usd(model: dict, input_tokens: int, output_tokens: int) -> float:
    long_prompt = "in_long" in model and input_tokens > 100_000
    rate_in = model["in_long"] if long_prompt else model["in"]
    rate_out = model["out_long"] if long_prompt else model["out"]
    return (input_tokens * rate_in + output_tokens * rate_out) / 1_000_000


st.set_page_config(page_title="8주 초과 치료 소견서 보조", page_icon="📝", layout="wide")
st.title("📝 8주 초과 치료 필요성 소견서 작성 보조")
st.caption("진료기록에 근거한 초안을 만듭니다. 최종 판단·수정·서명은 원장님이 하셔야 합니다.")

# ---------- 사이드바: 설정 ----------
with st.sidebar:
    st.header("설정")
    saved_key = load_saved_key()
    api_key = st.text_input("Anthropic API 키", value=saved_key, type="password")
    if api_key and api_key != saved_key and st.button("이 PC에 키 저장"):
        KEY_FILE.write_text(api_key.strip(), encoding="utf-8")
        st.success("api_key.txt에 저장했습니다.")
    model_label = st.selectbox("모델", list(MODELS))
    st.markdown("---")
    st.markdown("**서식**")
    st.text(prompts.TEMPLATE)

model = MODELS[model_label]

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
    client = anthropic.Anthropic(api_key=api_key.strip())
    st.session_state.pop("result", None)
    placeholder = st.empty()
    try:
        with client.messages.stream(
            model=model["id"],
            max_tokens=16000,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            system=prompts.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompts.build_user_message(masked_text, memo)}],
        ) as stream:
            streamed = ""
            for chunk in stream.text_stream:
                streamed += chunk
                placeholder.text(streamed)
            final = stream.get_final_message()
    except anthropic.AuthenticationError:
        st.error("API 키가 올바르지 않습니다. 키를 다시 확인해 주세요.")
        st.stop()
    except anthropic.PermissionDeniedError:
        st.error("이 API 키로는 해당 모델을 사용할 수 없습니다. 콘솔에서 권한·결제 상태를 확인해 주세요.")
        st.stop()
    except anthropic.RateLimitError:
        st.error("요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.")
        st.stop()
    except anthropic.APIStatusError as e:
        st.error(f"API 오류 ({e.status_code}): {e.message}")
        st.stop()
    except anthropic.APIConnectionError:
        st.error("인터넷 연결을 확인해 주세요.")
        st.stop()
    placeholder.empty()

    if final.stop_reason == "refusal":
        st.error("AI가 이 요청을 처리하지 않았습니다. 자료 내용을 확인하거나 다른 모델로 시도해 주세요.")
        st.stop()

    output = "".join(b.text for b in final.content if b.type == "text")
    draft, review = prompts.split_output(output)
    usage = final.usage
    st.session_state["result"] = {
        "draft": draft,
        "review": review,
        "truncated": final.stop_reason == "max_tokens",
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cost": cost_usd(model, usage.input_tokens, usage.output_tokens),
        "model": model_label,
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
    )
