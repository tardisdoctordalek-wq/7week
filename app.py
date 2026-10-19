"""자동차보험 경상환자 8주 초과 치료 필요성 소견서 작성 보조 앱.

실행: streamlit run app.py   (Windows는 실행.bat 더블클릭)
"""

import hashlib
import io
import os
from pathlib import Path

import streamlit as st
from pypdf import PdfReader

import llm
import prompts

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


RECORD_KINDS = ["통원", "입원", "진단서", "영상·검사", "기타"]


def guess_kind(filename: str) -> str:
    for word, kind in [("입원", "입원"), ("통원", "통원"), ("외래", "통원"), ("진단", "진단서"), ("영상", "영상·검사"), ("검사", "영상·검사")]:
        if word in filename:
            return kind
    return "통원"


def extract_pdf(name: str, kind: str, data: bytes) -> tuple[str, list[int]]:
    """쪽 표시를 붙인 텍스트와, 글자가 거의 없는(스캔 의심) 쪽 번호 목록을 돌려준다."""
    reader = PdfReader(io.BytesIO(data))
    chunks, empty_pages = [], []
    for i, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").strip()
        if len(text) < MIN_CHARS_PER_PAGE:
            empty_pages.append(i)
        chunks.append(f"=== [{kind}] {name} p.{i} ===\n{text}")
    return "\n\n".join(chunks), empty_pages


st.set_page_config(page_title="8주 초과 치료 소견서 보조", page_icon="📝", layout="wide")
st.title("📝 8주 초과 치료 필요성 소견서 작성 보조")
st.caption("진료기록에 근거한 초안을 만듭니다. 최종 판단·수정·서명은 원장님이 하셔야 합니다.")

# AI 요청 중에는 모든 입력을 잠가서, 버튼을 여러 번 누르거나 다른 입력을 바꿔도 요청이 중복되지 않게 한다.
st.session_state.setdefault("running", False)
st.session_state.setdefault("cache", {})  # 같은 입력으로 이미 받은 결과 (중복 비용 방지)
busy = st.session_state["running"]

# ---------- 사이드바: 설정 ----------
with st.sidebar:
    st.header("설정")
    model_label = st.selectbox("AI 모델", list(llm.MODELS), disabled=busy)
    model = llm.MODELS[model_label]
    provider = llm.PROVIDERS[model["provider"]]
    saved_key = load_saved_key(provider)
    api_key = st.text_input(
        f"{provider['name']} API 키", value=saved_key, type="password", key=f"key_{model['provider']}", disabled=busy
    )
    if api_key and api_key != saved_key and st.button("이 PC에 키 저장", disabled=busy):
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
    "비식별화한 진단서·진료기록부 PDF (입원·통원 기록 등 여러 개를 한 번에 올릴 수 있습니다)",
    type=["pdf"],
    accept_multiple_files=True,
    disabled=busy,
)
if not files:
    st.session_state["running"] = False
    st.info("PDF를 올려주세요. 원본 PDF는 이 PC 밖으로 나가지 않고, 추출한 글자만 AI로 전송됩니다.")
    st.stop()

st.markdown("**파일별 기록 종류** (AI가 입원·통원 기록을 구분해서 근거를 표시합니다)")
kinds = {}
for i, f in enumerate(files):
    name_col, kind_col = st.columns([3, 1])
    name_col.markdown(f"📄 {f.name}")
    default = guess_kind(f.name)
    kinds[f.name] = kind_col.selectbox(
        "종류", RECORD_KINDS, index=RECORD_KINDS.index(default), key=f"kind_{i}_{f.name}",
        label_visibility="collapsed", disabled=busy,
    )

texts, scanned = [], {}
for f in files:
    try:
        text, empty_pages = extract_pdf(f.name, kinds[f.name], f.getvalue())
    except Exception as e:  # 손상·암호 PDF 등
        st.session_state["running"] = False
        st.error(f"{f.name}: PDF를 읽지 못했습니다 ({e})")
        st.stop()
    texts.append(text)
    if empty_pages:
        scanned[f.name] = empty_pages

if scanned:
    detail = ", ".join(f"{name} p.{','.join(map(str, pages))}" for name, pages in scanned.items())
    st.warning(
        f"글자를 추출하지 못한 쪽이 있습니다: {detail}\n\n"
        "스캔(사진) PDF로 보입니다. 이 쪽들의 내용은 AI에 전달되지 않습니다. "
        "EMR에서 PDF로 직접 출력한 파일을 사용해 주세요."
    )

records = "\n\n".join(texts)

# ---------- 2. 전송 내용 확인 ----------
st.subheader("2. 전송 내용 확인")
with st.expander("AI에 전송될 내용 보기"):
    st.text_area("전송 내용", records, height=400, disabled=True, label_visibility="collapsed")
confirmed = st.checkbox("전송될 내용에 환자를 특정할 수 있는 정보가 없음을 확인했습니다.", disabled=busy)

# ---------- 3. 작성 ----------
st.subheader("3. 소견서 초안 작성")
memo = st.text_area(
    "원장님 메모 (선택)",
    placeholder="기록에 없지만 반영할 내용. 예) 향후 4주간 주 3회 침·추나 치료 계획",
    height=80,
    disabled=busy,
)

request_id = hashlib.sha256("\x00".join([model["id"], records, memo]).encode()).hexdigest()
already_done = request_id in st.session_state["cache"]


def start(force: bool = False) -> None:
    # 버튼을 누른 순간 바로 잠근다. 다음 화면부터 버튼이 비활성화된다.
    st.session_state["running"] = True
    st.session_state["force"] = force


ready = confirmed and bool(api_key)
col_a, col_b = st.columns([1, 4])
col_a.button("초안 작성", type="primary", disabled=busy or not ready, on_click=start)
if already_done:
    col_b.button("같은 내용으로 다시 작성 (비용 다시 발생)", disabled=busy or not ready, on_click=start, args=(True,))

if busy:
    force = st.session_state.pop("force", False)
    try:
        if already_done and not force:
            # 같은 입력으로 이미 받은 결과가 있으면 다시 요청하지 않는다.
            st.session_state["result"] = st.session_state["cache"][request_id] | {"reused": True}
        else:
            placeholder = st.empty()
            streamed = []

            def show(chunk: str) -> None:
                streamed.append(chunk)
                placeholder.text("".join(streamed))

            with st.spinner("AI가 작성 중입니다. 끝날 때까지 입력이 잠깁니다..."):
                res = llm.generate(
                    model, api_key.strip(), prompts.SYSTEM_PROMPT, prompts.build_user_message(records, memo), show
                )
            draft, review = prompts.split_output(res.text)
            result = {
                "draft": draft,
                "review": review,
                "truncated": res.truncated,
                "input_tokens": res.input_tokens,
                "output_tokens": res.output_tokens,
                "cost": llm.cost_usd(model, res.input_tokens, res.output_tokens),
                "model": model_label,
                "provider": model["provider"],
            }
            st.session_state["cache"][request_id] = result
            st.session_state["result"] = result | {"reused": False}
        st.session_state.pop("error", None)
    except llm.LLMError as e:
        st.session_state["error"] = str(e)
    finally:
        st.session_state["running"] = False
    st.rerun()

if st.session_state.get("error"):
    st.error(st.session_state["error"])

result = st.session_state.get("result")
if result:
    if result.get("reused"):
        st.info("같은 내용으로 이미 작성한 결과를 다시 보여드립니다. 추가 비용은 없습니다.")
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
