from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

import anthropic
from anthropic.types.beta import BetaMessageParam, BetaTextBlockParam, BetaToolParam

from rhizo.config import settings

StopReason = Literal["end_turn", "tool_use", "max_tokens", "refusal", "other"]

_FALLBACK_MODELS = frozenset({"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"})
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMUnavailable(Exception): ...


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ToolReply:
    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class Turn:
    text: str
    tool_calls: list[ToolCall]
    stop_reason: StopReason


class Conversation(Protocol):
    async def ask(self, text: str) -> Turn: ...

    async def reply(self, results: list[ToolReply]) -> Turn: ...


class LLM(Protocol):
    def conversation(self, system: str, tools: list[dict[str, Any]]) -> Conversation: ...


def _stop_reason(raw: str | None) -> StopReason:
    return raw if raw in ("end_turn", "tool_use", "max_tokens", "refusal") else "other"  # type: ignore[return-value]


class _AnthropicConversation:
    def __init__(self, llm: "AnthropicLLM", system: str, tools: list[dict[str, Any]]) -> None:
        self._llm = llm
        self._tools = cast(list[BetaToolParam], tools)
        self._system: list[BetaTextBlockParam] = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
        self._messages: list[BetaMessageParam] = []

    async def ask(self, text: str) -> Turn:
        self._messages.append({"role": "user", "content": text})
        return await self._call()

    async def reply(self, results: list[ToolReply]) -> Turn:
        self._messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": r.tool_call_id,
                        "content": r.content,
                        "is_error": r.is_error,
                    }
                    for r in results
                ],
            }
        )
        return await self._call()

    async def _call(self) -> Turn:
        model = self._llm.model
        fallback = model in _FALLBACK_MODELS
        try:
            response = await self._llm.client.beta.messages.create(
                model=model,
                max_tokens=settings.llm_max_tokens,
                system=self._system,
                tools=self._tools,
                messages=self._messages,
                output_config={"effort": settings.llm_effort},
                betas=[_FALLBACK_BETA] if fallback else anthropic.omit,
                fallbacks="default" if fallback else anthropic.omit,
            )
        except (anthropic.APIConnectionError, anthropic.APIStatusError) as e:
            raise LLMUnavailable(f"LLM request failed: {type(e).__name__}") from e
        self._messages.append({"role": "assistant", "content": response.content})
        return Turn(
            text="".join(b.text for b in response.content if b.type == "text"),
            tool_calls=[
                ToolCall(id=b.id, name=b.name, input=dict(b.input))
                for b in response.content
                if b.type == "tool_use"
            ],
            stop_reason=_stop_reason(response.stop_reason),
        )


class AnthropicLLM:
    def __init__(self, model: str, api_key: str) -> None:
        if not model:
            raise LLMUnavailable("LLM_MODEL is not set")
        self.model = model
        self.client = anthropic.AsyncAnthropic(api_key=api_key or None)

    def conversation(self, system: str, tools: list[dict[str, Any]]) -> Conversation:
        return _AnthropicConversation(self, system, tools)


def default_llm() -> LLM:
    try:
        return AnthropicLLM(settings.llm_model, settings.anthropic_api_key)
    except anthropic.AnthropicError as e:
        raise LLMUnavailable(str(e)) from e
