import json
import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from rhizo.agent import grounding, registry
from rhizo.agent.llm import LLMUnavailable, ToolCall, ToolReply, Turn
from rhizo.agent.prompt import GROUNDING_RETRY
from rhizo.api.routes import agent as agent_route
from rhizo.config import settings
from rhizo.graph.client import GraphClient

Event = tuple[str, dict[str, Any]]


class FakeLLM:
    def __init__(self, *turns: Turn) -> None:
        self.turns = list(turns)
        self.sent: list[str | list[ToolReply]] = []
        self.tools: list[dict[str, Any]] = []

    def conversation(self, system: str, tools: list[dict[str, Any]]) -> "FakeLLM":
        self.tools = tools
        return self

    async def ask(self, text: str) -> Turn:
        self.sent.append(text)
        return self._next()

    async def reply(self, results: list[ToolReply]) -> Turn:
        self.sent.append(results)
        return self._next()

    def _next(self) -> Turn:
        assert self.turns, "the loop asked the model for more turns than the test scripted"
        return self.turns.pop(0)


def _say(text: str) -> Turn:
    return Turn(text=text, tool_calls=[], stop_reason="end_turn")


def _call(name: str, **args: object) -> Turn:
    return Turn(
        text="",
        tool_calls=[ToolCall(id=f"toolu_{name}", name=name, input=dict(args))],
        stop_reason="tool_use",
    )


def _replies(llm: FakeLLM, index: int) -> list[ToolReply]:
    sent = llm.sent[index]
    assert isinstance(sent, list)
    return sent


@pytest.fixture
def llm_mode(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "agent_mode", "llm")
    monkeypatch.setattr(settings, "agent_token_delay_ms", 0)
    yield


def _use(monkeypatch: pytest.MonkeyPatch, llm: FakeLLM) -> None:
    monkeypatch.setattr(agent_route, "default_llm", lambda: llm)


def _ask(api: TestClient, question: str) -> list[Event]:
    res = api.post("/api/agent/ask", json={"question": question})
    assert res.status_code == 200, res.text
    events = []
    for frame in res.text.split("\n\n"):
        if frame.strip():
            event = re.search(r"^event: (.+)$", frame, re.M)
            data = re.search(r"^data: (.+)$", frame, re.M)
            assert event and data
            events.append((event[1], json.loads(data[1])))
    return events


def _answer(events: list[Event]) -> str:
    return "".join(d["text"] for k, d in events if k == "answer_token")


def _kinds(events: list[Event]) -> list[str]:
    out: list[str] = []
    for kind, _ in events:
        if not (kind == "answer_token" and out and out[-1] == "answer_token"):
            out.append(kind)
    return out


def test_ungrounded_names_are_whole_tokens_not_in_the_allow_list() -> None:
    known = ["frontend", "paymentservice", "redis-cart"]
    text = "frontend breaks; the payment service and frontends are fine."
    assert grounding.ungrounded(text, known, allowed={"frontend"}) == ["paymentservice"]


def test_strip_drops_unsupported_sentences_and_bullets_and_says_so() -> None:
    text = "A breaks. X is also down.\n- A: 1 hop\n- X: 2 hops"
    assert grounding.strip(text, ["X"]) == f"A breaks.\n- A: 1 hop\n\n{grounding.NOTE}"


def test_llm_answer_streams_tool_events_then_grounded_tokens(
    api: TestClient, tiny_graph: GraphClient, llm_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = FakeLLM(_call("get_blast_radius", service="C"), _say("If C fails, B and A break (inferred)."))
    _use(monkeypatch, llm)
    events = _ask(api, "What breaks if C fails?")
    assert _kinds(events) == ["tool_call", "tool_result", "graph_path", "answer_token", "done"]
    assert _answer(events) == "If C fails, B and A break (inferred)."
    assert events[-1][1]["basis"] == "inferred"
    [reply] = _replies(llm, 1)
    assert {i["service"]["name"] for i in json.loads(reply.content)["result"]["items"]} == {"A", "B"}
    assert {t["name"] for t in llm.tools} == set(registry.TOOLS)


def test_ungrounded_answer_is_corrected_by_one_retry(
    api: TestClient, tiny_graph: GraphClient, llm_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = FakeLLM(
        _call("get_blast_radius", service="C"),
        _say("B and A break, and D too."),
        _say("B and A break."),
    )
    _use(monkeypatch, llm)
    events = _ask(api, "What breaks if C fails?")
    assert llm.sent[2] == GROUNDING_RETRY.format(names="D")
    assert _answer(events) == "B and A break."


def test_still_ungrounded_after_retry_is_stripped(
    api: TestClient, tiny_graph: GraphClient, llm_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(
        monkeypatch,
        FakeLLM(
            _call("get_blast_radius", service="C"), _say("B breaks. D breaks."), _say("B breaks. D breaks.")
        ),
    )
    assert _answer(_ask(api, "What breaks if C fails?")) == f"B breaks.\n\n{grounding.NOTE}"


def test_no_tool_data_means_insufficient_data_not_an_answer(
    api: TestClient, tiny_graph: GraphClient, llm_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, FakeLLM(_say("I think it is probably fine.")))
    events = _ask(api, "Is everything ok?")
    assert _kinds(events) == ["insufficient_data", "done"]
    assert events[-1][1]["basis"] == "n/a"


def test_bad_tool_arguments_go_back_to_the_model_as_an_error(
    api: TestClient, tiny_graph: GraphClient, llm_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = FakeLLM(
        _call("get_blast_radius", service="nope"),
        _call("get_blast_radius", service="C"),
        _say("B and A break."),
    )
    _use(monkeypatch, llm)
    events = _ask(api, "What breaks if C fails?")
    failed = next(d for k, d in events if k == "tool_result")
    assert failed["summary"].startswith("failed: no service or resource named nope")
    [error_reply] = _replies(llm, 1)
    assert error_reply.is_error
    assert _answer(events) == "B and A break."


def test_refusal_is_reported_as_insufficient_data(
    api: TestClient, tiny_graph: GraphClient, llm_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, FakeLLM(Turn(text="", tool_calls=[], stop_reason="refusal")))
    assert _kinds(_ask(api, "What breaks if C fails?")) == ["insufficient_data", "done"]


def test_unavailable_llm_falls_back_to_the_scripted_agent(
    api: TestClient, tiny_graph: GraphClient, llm_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> FakeLLM:
        raise LLMUnavailable("ANTHROPIC_API_KEY is not set")

    monkeypatch.setattr(agent_route, "default_llm", broken)
    events = _ask(api, "What breaks if C fails?")
    assert events[0] == ("error", {"message": "ANTHROPIC_API_KEY is not set. Answering in scripted mode."})
    assert [d["name"] for k, d in events if k == "tool_call"] == ["get_blast_radius", "recommend_responders"]
    assert events[-1][0] == "done"


def test_llm_mode_returns_503_before_streaming_when_falkordb_is_unreachable(
    api_db_down: TestClient, llm_mode: None
) -> None:
    res = api_db_down.post("/api/agent/ask", json={"question": "What breaks if C fails?"})
    assert (res.status_code, res.json()["error"]["code"]) == (503, "UPSTREAM")


def test_tool_schemas_are_generated_from_the_arg_models() -> None:
    schemas = {s["name"]: s for s in registry.tool_schemas()}
    assert set(schemas) == set(registry.TOOLS)
    assert schemas["get_blast_radius"]["input_schema"]["required"] == ["service"]
    assert all(s["input_schema"]["type"] == "object" for s in schemas.values())
