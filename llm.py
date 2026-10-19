"""Claude(Anthropic)와 Gemini(Google) 호출을 같은 형태로 감싼다."""

from dataclasses import dataclass
from typing import Callable

import anthropic
import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

MAX_OUTPUT_TOKENS = 16000

# 100만 토큰당 USD (유료 기준). Gemini 무료 키로 쓰면 실제 청구액은 0원이다.
MODELS = {
    "Claude Haiku 5.5": {
        "provider": "anthropic", "id": "claude-haiku-5-5",
        "in": 0.10, "out": 0.50, "long_threshold": 100_000, "in_long": 0.50, "out_long": 2.50,
    },
    "Claude Sonnet 5.5": {"provider": "anthropic", "id": "claude-sonnet-5-5", "in": 2.00, "out": 10.00},
    "Gemini 3.5 Flash-Lite": {"provider": "google", "id": "gemini-3.5-flash-lite", "in": 0.30, "out": 2.50},
    # 2026-12-31까지 할인가. 2027-01-01부터 $1.50 / $7.50.
    "Gemini 3.8 Flash": {"provider": "google", "id": "gemini-3.8-flash", "in": 0.75, "out": 3.75},
}

PROVIDERS = {
    "anthropic": {
        "name": "Anthropic (Claude)", "key_file": "api_key.txt", "env": ["ANTHROPIC_API_KEY"], "prefix": "sk-ant-",
    },
    "google": {
        "name": "Google AI Studio (Gemini)", "key_file": "gemini_key.txt", "env": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "prefix": "AIza",
    },
}


def check_key(provider: dict, key: str) -> tuple[str | None, str | None]:
    """(오류, 경고)를 돌려준다. 오류가 있으면 그 키는 쓸 수 없다."""
    if not key.isascii() or any(c.isspace() for c in key):
        return "키에 띄어쓰기나 한글 등 키가 아닌 글자가 들어 있습니다. 키만 다시 복사해 붙여넣어 주세요.", None
    if not key.startswith(provider["prefix"]):
        return None, f"{provider['name']} 키는 보통 '{provider['prefix']}'로 시작합니다. 맞는 키인지 확인해 주세요."
    return None, None


class LLMError(Exception):
    """사용자에게 그대로 보여줄 수 있는 오류."""


@dataclass
class Result:
    text: str
    input_tokens: int
    output_tokens: int  # 사고과정(thinking) 토큰 포함
    truncated: bool


def cost_usd(model: dict, input_tokens: int, output_tokens: int) -> float:
    long_prompt = "long_threshold" in model and input_tokens > model["long_threshold"]
    rate_in = model["in_long"] if long_prompt else model["in"]
    rate_out = model["out_long"] if long_prompt else model["out"]
    return (input_tokens * rate_in + output_tokens * rate_out) / 1_000_000


def generate(model: dict, api_key: str, system: str, user: str, on_text: Callable[[str], None]) -> Result:
    if model["provider"] == "anthropic":
        return _generate_anthropic(model["id"], api_key, system, user, on_text)
    return _generate_google(model["id"], api_key, system, user, on_text)


def _generate_anthropic(model_id, api_key, system, user, on_text) -> Result:
    client = anthropic.Anthropic(api_key=api_key)
    try:
        with client.messages.stream(
            model=model_id,
            max_tokens=MAX_OUTPUT_TOKENS,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            for chunk in stream.text_stream:
                on_text(chunk)
            final = stream.get_final_message()
    except anthropic.AuthenticationError:
        raise LLMError("API 키가 올바르지 않습니다. 키를 다시 확인해 주세요.")
    except anthropic.PermissionDeniedError:
        raise LLMError("이 API 키로는 해당 모델을 사용할 수 없습니다. 콘솔에서 권한·결제 상태를 확인해 주세요.")
    except anthropic.RateLimitError:
        raise LLMError("요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.")
    except anthropic.APIStatusError as e:
        raise LLMError(f"API 오류 ({e.status_code}): {e.message}")
    except anthropic.APIConnectionError:
        raise LLMError("인터넷 연결을 확인해 주세요.")

    if final.stop_reason == "refusal":
        raise LLMError("AI가 이 요청을 처리하지 않았습니다. 자료 내용을 확인하거나 다른 모델로 시도해 주세요.")
    return Result(
        text="".join(b.text for b in final.content if b.type == "text"),
        input_tokens=final.usage.input_tokens,
        output_tokens=final.usage.output_tokens,
        truncated=final.stop_reason == "max_tokens",
    )


_GOOGLE_BLOCKED = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION", "OTHER"}


def _generate_google(model_id, api_key, system, user, on_text) -> Result:
    client = genai.Client(api_key=api_key)
    config = genai_types.GenerateContentConfig(system_instruction=system, max_output_tokens=MAX_OUTPUT_TOKENS)
    text, usage, finish = "", None, None
    try:
        for chunk in client.models.generate_content_stream(model=model_id, contents=user, config=config):
            if chunk.prompt_feedback and chunk.prompt_feedback.block_reason:
                raise LLMError("Gemini가 이 요청을 차단했습니다. 자료 내용을 확인하거나 다른 모델로 시도해 주세요.")
            if chunk.text:
                text += chunk.text
                on_text(chunk.text)
            if chunk.usage_metadata:
                usage = chunk.usage_metadata
            if chunk.candidates and chunk.candidates[0].finish_reason:
                finish = chunk.candidates[0].finish_reason.name
    except genai_errors.ClientError as e:
        if e.code == 429:
            raise LLMError("요청 한도를 초과했습니다. 무료 키는 분당·하루 요청 수 제한이 있습니다. 잠시 후 다시 시도해 주세요.")
        if e.code in (400, 401, 403) and "key" in str(e).lower():
            raise LLMError("API 키가 올바르지 않습니다. Google AI Studio에서 키를 다시 확인해 주세요.")
        if e.code == 404:
            raise LLMError(f"모델 '{model_id}'을(를) 찾을 수 없습니다. 모델 이름이 바뀌었을 수 있습니다.")
        raise LLMError(f"Gemini API 오류 ({e.code}): {e.message}")
    except genai_errors.ServerError as e:
        raise LLMError(f"Gemini 서버 오류 ({e.code}). 잠시 후 다시 시도해 주세요.")
    except genai_errors.APIError as e:
        raise LLMError(f"Gemini API 오류 ({e.code}): {e.message}")
    except httpx.TransportError:
        raise LLMError("인터넷 연결을 확인해 주세요.")

    if finish in _GOOGLE_BLOCKED:
        raise LLMError(f"Gemini가 응답을 중단했습니다 (사유: {finish}). 다른 모델로 시도해 주세요.")
    return Result(
        text=text,
        input_tokens=(usage.prompt_token_count or 0) if usage else 0,
        output_tokens=((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)) if usage else 0,
        truncated=finish == "MAX_TOKENS",
    )
