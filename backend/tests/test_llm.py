from types import SimpleNamespace
from typing import Any

import anyio
import pytest

from rhizo.agent.llm import AnthropicLLM, LLMUnavailable, ToolReply


class StubMessages:
    def __init__(self, *responses: SimpleNamespace) -> None:
        self.responses: list[SimpleNamespace] = list(responses)
        self.requests: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        self.requests.append(kwargs)
        return self.responses.pop(0)


def _response(*blocks: SimpleNamespace, stop: str) -> SimpleNamespace:
    return SimpleNamespace(content=list(blocks), stop_reason=stop)


def _llm(model: str, stub: StubMessages) -> AnthropicLLM:
    llm = AnthropicLLM(model, api_key="test-key")
    llm.client = SimpleNamespace(beta=SimpleNamespace(messages=stub))  # type: ignore[assignment]
    return llm


def test_tool_round_trip_request_shape() -> None:
    thinking = SimpleNamespace(type="thinking", thinking="", signature="sig")
    tool_use = SimpleNamespace(type="tool_use", id="toolu_1", name="get_blast_radius", input={"service": "C"})
    stub = StubMessages(
        _response(thinking, tool_use, stop="tool_use"),
        _response(SimpleNamespace(type="text", text="B breaks."), stop="end_turn"),
    )
    conv = _llm("claude-opus-5-5", stub).conversation("system prompt", [{"name": "get_blast_radius"}])

    async def scenario() -> None:
        first = await conv.ask("What breaks if C fails?")
        assert first.stop_reason == "tool_use" and first.tool_calls[0].input == {"service": "C"}
        final = await conv.reply(
            [ToolReply("toolu_1", '{"ok":1}'), ToolReply("toolu_2", "bad", is_error=True)]
        )
        assert (final.text, final.stop_reason) == ("B breaks.", "end_turn")

    anyio.run(scenario)
    req = stub.requests[1]
    assert req["model"] == "claude-opus-5-5"
    assert req["output_config"] == {"effort": "medium"}
    assert req["betas"] == ["server-side-fallback-2026-07-01"] and req["fallbacks"] == "default"
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    messages = req["messages"]
    assert messages[1] == {"role": "assistant", "content": [thinking, tool_use]}
    assert [r["tool_use_id"] for r in messages[2]["content"]] == ["toolu_1", "toolu_2"]
    assert messages[2]["content"][1]["is_error"] is True


def test_models_without_fallback_support_omit_it() -> None:
    stub = StubMessages(_response(SimpleNamespace(type="text", text="ok"), stop="end_turn"))
    anyio.run(_llm("claude-haiku-5-5", stub).conversation("s", []).ask, "q")
    assert "betas" not in {k for k, v in stub.requests[0].items() if v.__class__.__name__ != "Omit"}


def test_missing_model_is_unavailable() -> None:
    with pytest.raises(LLMUnavailable):
        AnthropicLLM("", api_key="test-key")
