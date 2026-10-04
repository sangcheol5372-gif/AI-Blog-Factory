"""Claude API 호출을 한 곳에 모은다. 응답은 항상 JSON 스키마로 받는다."""
import json

MODEL = "claude-opus-5-5"
# 안전 분류기가 요청을 거절하면 서버가 권장 모델로 자동 재시도한다.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    pass


def make_client():
    import anthropic  # 키가 없는 환경에서도 1·2단계는 돌아가도록 지연 import
    return anthropic.Anthropic()


def _stream(client, system: str, user: str, schema: dict, effort: str):
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=64000,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        cache_control={"type": "ephemeral"},
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    ) as stream:
        return stream.get_final_message()


def _friendly(e: Exception) -> LLMError | None:
    if isinstance(e, TypeError) and "authentication" in str(e):
        return LLMError("Anthropic API 인증 정보 없음 — .env 에 ANTHROPIC_API_KEY 를 넣으세요")
    try:
        import anthropic
    except ImportError:
        return None
    if isinstance(e, anthropic.AuthenticationError):
        return LLMError("Anthropic API 키가 올바르지 않음")
    if isinstance(e, anthropic.RateLimitError):
        return LLMError("요청 한도 초과 — 잠시 후 다시 실행")
    if isinstance(e, anthropic.APIStatusError):
        return LLMError(f"API 오류 {e.status_code}: {e.message}")
    if isinstance(e, anthropic.APIConnectionError):
        return LLMError("API 연결 실패 — 네트워크 확인")
    return None


def call_json(system: str, user: str, schema: dict, *, effort: str = "high", client=None) -> dict:
    """system/user 프롬프트로 호출해 schema 에 맞는 JSON 을 돌려받는다."""
    try:
        msg = _stream(client or make_client(), system, user, schema, effort)
    except Exception as e:
        if (friendly := _friendly(e)) is not None:
            raise friendly from e
        raise
    if msg.stop_reason == "refusal":
        cat = getattr(msg.stop_details, "category", None) if msg.stop_details else None
        raise LLMError(f"모델이 요청을 거절함 (category={cat})")
    if msg.stop_reason == "max_tokens":
        raise LLMError("출력이 max_tokens 에서 잘림")
    text = next((b.text for b in msg.content if b.type == "text"), None)
    if text is None:
        raise LLMError(f"텍스트 응답 없음 (stop_reason={msg.stop_reason})")
    return json.loads(text)
