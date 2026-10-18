import json
import re

import pytest
from fastapi.testclient import TestClient

from rhizo.agent import registry
from rhizo.agent.scripted import mentioned
from rhizo.config import settings
from rhizo.graph.client import GraphClient

Event = tuple[str, dict[str, object]]


@pytest.fixture(autouse=True)
def _no_token_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "agent_token_delay_ms", 0)


def _ask(api: TestClient, question: str, **context: str) -> list[Event]:
    res = api.post("/api/agent/ask", json={"question": question, "context": context or None})
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("text/event-stream")
    assert res.headers["cache-control"] == "no-cache" and res.headers["x-accel-buffering"] == "no"
    events = []
    for frame in res.text.split("\n\n"):
        if frame.strip():
            event = re.search(r"^event: (.+)$", frame, re.M)
            data = re.search(r"^data: (.+)$", frame, re.M)
            assert event and data, frame
            events.append((event[1], json.loads(data[1])))
    return events


def _shape(events: list[Event]) -> list[str]:
    out: list[str] = []
    for kind, _ in events:
        if not (kind == "answer_token" and out and out[-1] == "answer_token"):
            out.append(kind)
    return out


def _answer(events: list[Event]) -> str:
    return "".join(str(d["text"]) for k, d in events if k == "answer_token")


def test_blast_radius_question_streams_events_in_order(api: TestClient, tiny_graph: GraphClient) -> None:
    events = _ask(api, "What breaks if C fails?")
    assert _shape(events) == [
        "tool_call",
        "tool_result",
        "graph_path",
        "tool_call",
        "tool_result",
        "answer_token",
        "done",
    ]
    calls = [d for k, d in events if k == "tool_call"]
    assert [c["name"] for c in calls] == ["get_blast_radius", "recommend_responders"]
    results = [d for k, d in events if k == "tool_result"]
    assert [r["id"] for r in results] == [c["id"] for c in calls]
    evidence = results[0]["evidence"]
    assert isinstance(evidence, dict)
    assert evidence["cypher"] and set(evidence["returned_ids"]) == {"svc:A", "svc:B"}

    path = next(d for k, d in events if k == "graph_path")
    assert path["edge_ids"] == ["DEPENDS_ON:svc:B->svc:C", "DEPENDS_ON:svc:A->svc:B"]
    assert all(len(str(d["text"])) <= 6 for k, d in events if k == "answer_token")
    assert "If **C** fails, **2 services** break: B and A." in _answer(events)
    assert events[-1][1]["basis"] == "inferred"


@pytest.mark.parametrize(
    ("question", "tools"),
    [
        ("Why is A returning 5xx errors?", ["get_upstream_suspects", "find_similar_incidents"]),
        ("Find hidden dependencies nobody declared", ["find_hidden_dependencies"]),
        ("Which services are the most critical?", ["rank_criticality"]),
        ("What breaks if R goes down?", ["get_blast_radius", "recommend_responders"]),
    ],
)
def test_router_picks_the_right_tools(
    api: TestClient, tiny_graph: GraphClient, question: str, tools: list[str]
) -> None:
    events = _ask(api, question)
    assert [d["name"] for k, d in events if k == "tool_call"] == tools
    assert events[-1][0] == "done" and _answer(events)


def test_hidden_answer_is_grounded_in_tool_results(api: TestClient, tiny_graph: GraphClient) -> None:
    answer = _answer(_ask(api, "Find hidden dependencies nobody declared"))
    assert "**C ↔ D**" in answer and "*inferred*" in answer


def test_context_service_is_used_when_the_question_names_none(
    api: TestClient, tiny_graph: GraphClient
) -> None:
    events = _ask(api, "What breaks if this fails?", service="B")
    call = next(d for k, d in events if k == "tool_call")
    assert call["args"] == {"service": "B", "max_hops": 4, "min_confidence": 0.5}


def test_unknown_subject_is_insufficient_data(api: TestClient, tiny_graph: GraphClient) -> None:
    events = _ask(api, "Is the weather nice?")
    assert _shape(events) == ["insufficient_data", "done"]
    assert events[-1][1]["basis"] == "n/a"


def test_tools_are_read_only(tiny_graph: GraphClient) -> None:
    graphs = registry.Graphs(tiny_graph.topology(), tiny_graph.memory())
    args: dict[str, dict[str, object]] = {
        "get_blast_radius": {"service": "C"},
        "get_upstream_suspects": {"service": "A"},
        "find_hidden_dependencies": {},
        "rank_criticality": {},
        "recommend_responders": {"services": ["C"]},
        "find_similar_incidents": {"services": ["C"]},
    }
    assert set(registry.TOOLS) == set(args)
    cypher = [
        c for name, tool_args in args.items() for c in registry.call(name, graphs, tool_args).evidence.cypher
    ]
    writes = re.compile(r"\b(CREATE|MERGE|SET|DELETE|REMOVE)\b")
    assert cypher and not [c for c in cypher if writes.search(c)]


def test_mention_matching() -> None:
    names = ["paymentservice", "frontend", "redis-cart"]
    assert mentioned("why is the payment service slow", names) == "paymentservice"
    assert mentioned("frontend calls paymentservice", names) == "frontend"
    assert mentioned("nothing here", names) is None
    assert mentioned("the frontends team", names) is None
    assert mentioned("is redis-cart down?", names) == "redis-cart"


def test_ask_returns_503_before_streaming_when_falkordb_is_unreachable(api_db_down: TestClient) -> None:
    res = api_db_down.post("/api/agent/ask", json={"question": "What breaks if C fails?"})
    assert (res.status_code, res.json()["error"]["code"]) == (503, "UPSTREAM")


def test_ask_validates_input(api: TestClient, tiny_graph: GraphClient) -> None:
    assert api.post("/api/agent/ask", json={"question": ""}).status_code == 400
    assert (
        api.post("/api/agent/ask", json={"question": "x", "context": {"service": "a b"}}).status_code == 400
    )
