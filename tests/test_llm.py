import sys
from pathlib import Path

import pytest
from google.genai import errors as genai_errors
from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import llm  # noqa: E402

GEMINI = llm.MODELS["Gemini 3.5 Flash-Lite"]


def _chunk(text=None, finish=None, usage=None):
    parts = [types.Part(text=text)] if text else []
    cand = types.Candidate(content=types.Content(role="model", parts=parts), finish_reason=finish)
    return types.GenerateContentResponse(candidates=[cand], usage_metadata=usage)


class _FakeModels:
    def __init__(self, chunks=None, error=None):
        self.chunks, self.error, self.calls = chunks or [], error, []

    def generate_content_stream(self, model, contents, config):
        self.calls.append((model, contents, config))
        if self.error:
            raise self.error
        yield from self.chunks


def _patch_client(monkeypatch, fake):
    class FakeClient:
        def __init__(self, api_key):
            self.models = fake

    monkeypatch.setattr(llm.genai, "Client", FakeClient)


def test_gemini_streams_text_and_counts_thinking_tokens(monkeypatch):
    usage = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=1000, candidates_token_count=200, thoughts_token_count=300
    )
    fake = _FakeModels([_chunk("안녕"), _chunk("하세요", finish="STOP", usage=usage)])
    _patch_client(monkeypatch, fake)
    seen = []
    res = llm.generate(GEMINI, "k", "sys", "user", seen.append)
    assert res.text == "안녕하세요" and seen == ["안녕", "하세요"]
    assert (res.input_tokens, res.output_tokens, res.truncated) == (1000, 500, False)
    model_id, contents, config = fake.calls[0]
    assert model_id == "gemini-3.5-flash-lite" and config.system_instruction == "sys"


def test_gemini_safety_stop_is_error(monkeypatch):
    _patch_client(monkeypatch, _FakeModels([_chunk(finish="SAFETY")]))
    with pytest.raises(llm.LLMError, match="SAFETY"):
        llm.generate(GEMINI, "k", "s", "u", lambda _: None)


def test_gemini_rate_limit_message(monkeypatch):
    err = genai_errors.ClientError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})
    _patch_client(monkeypatch, _FakeModels(error=err))
    with pytest.raises(llm.LLMError, match="요청 한도"):
        llm.generate(GEMINI, "k", "s", "u", lambda _: None)


def test_gemini_bad_key_message(monkeypatch):
    err = genai_errors.ClientError(
        400, {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT"}}
    )
    _patch_client(monkeypatch, _FakeModels(error=err))
    with pytest.raises(llm.LLMError, match="API 키가 올바르지"):
        llm.generate(GEMINI, "k", "s", "u", lambda _: None)


def test_cost():
    haiku = llm.MODELS["Claude Haiku 5.5"]
    assert llm.cost_usd(haiku, 100_000, 100_000) == pytest.approx(0.06)
    assert llm.cost_usd(haiku, 200_000, 0) == pytest.approx(0.10)  # 10만 토큰 초과 단가
    assert llm.cost_usd(GEMINI, 1_000_000, 1_000_000) == pytest.approx(2.80)


def test_check_key():
    google = llm.PROVIDERS["google"]
    assert llm.check_key(google, "AIzaSyExample123") == (None, None)
    err, _ = llm.check_key(google, "Connection error Is Streamlit still running?")
    assert err and "띄어쓰기" in err
    err, warn = llm.check_key(google, "sk-ant-abc")
    assert err is None and "AIza" in warn
