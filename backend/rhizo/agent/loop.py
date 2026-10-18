import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

import anyio
from pydantic import BaseModel, ValidationError
from pydantic_core import to_jsonable_python

from rhizo.agent import grounding, registry
from rhizo.agent.llm import LLM, LLMUnavailable, ToolCall, ToolReply, Turn
from rhizo.agent.prompt import GROUNDING_RETRY, SYSTEM_PROMPT
from rhizo.agent.scripted import Insufficient, Plan
from rhizo.config import settings
from rhizo.core.errors import RhizoError, UpstreamError
from rhizo.graph.scoring import worst_basis
from rhizo.models import Evidence

log = logging.getLogger("rhizo.agent")

TOKEN_CHARS = 6
NO_BASIS = "The graph has no basis for an answer: no tool returned data for this question."

Disconnected = Callable[[], Awaitable[bool]]


def sse(event: str, data: BaseModel | dict[str, Any]) -> str:
    payload = to_jsonable_python(data, by_alias=True, exclude_none=True)
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


def _done(basis: str, t0: float) -> str:
    return sse("done", {"basis": basis, "took_ms": round((perf_counter() - t0) * 1000)})


def _tool_events(tool_id: str, result: registry.ToolResult) -> list[str]:
    events = [
        sse(
            "tool_result",
            {
                "id": tool_id,
                "duration_ms": result.duration_ms,
                "summary": result.summary,
                "evidence": result.evidence,
            },
        )
    ]
    if result.highlight and result.highlight.node_ids:
        events.append(sse("graph_path", result.highlight))
    return events


async def _answer(text: str) -> AsyncIterator[str]:
    delay = settings.agent_token_delay_ms / 1000
    for i in range(0, len(text), TOKEN_CHARS):
        yield sse("answer_token", {"text": text[i : i + TOKEN_CHARS]})
        if delay:
            await asyncio.sleep(delay)


async def stream_scripted(
    plan: Plan | Insufficient, graphs: registry.Graphs, disconnected: Disconnected
) -> AsyncIterator[str]:
    t0 = perf_counter()
    if isinstance(plan, Insufficient):
        yield sse("insufficient_data", {"reason": plan.reason})
        yield _done("n/a", t0)
        return

    results: list[registry.ToolResult] = []
    try:
        for k, step in enumerate(plan.steps, 1):
            if await disconnected():
                log.info("agent: client went away after %d tool(s)", k - 1)
                return
            tool_id, args = f"toolu_{k}", step.args(results)
            yield sse("tool_call", {"id": tool_id, "name": step.tool, "args": args})
            result = await anyio.to_thread.run_sync(registry.call, step.tool, graphs, args)
            results.append(result)
            for event in _tool_events(tool_id, result):
                yield event
        text = plan.answer(results)
    except RhizoError as e:
        yield sse("error", {"message": e.message})
        yield _done("n/a", t0)
        return

    async for token in _answer(text):
        yield token
    yield _done(worst_basis([r.basis for r in results]), t0)


@dataclass
class _Run:
    results: list[registry.ToolResult] = field(default_factory=list)
    asked_about: set[str] = field(default_factory=set)

    @property
    def allowed(self) -> set[str]:
        returned = grounding.names_from_ids([i for r in self.results for i in r.evidence.returned_ids])
        return returned | self.asked_about


def _asked_about(args: dict[str, Any]) -> set[str]:
    names = [args.get("service"), *(args.get("services") or [])]
    return {n for n in names if isinstance(n, str)}


async def _run_tool(call: ToolCall, graphs: registry.Graphs, run: _Run) -> tuple[list[str], ToolReply]:
    try:
        result = await anyio.to_thread.run_sync(registry.call, call.name, graphs, call.input)
    except UpstreamError:
        raise
    except (RhizoError, ValidationError) as e:
        message = e.message if isinstance(e, RhizoError) else f"invalid arguments: {e.errors()[0]['msg']}"
        failed = Evidence(cypher=[], params=call.input, returned_ids=[], note=message)
        event = sse(
            "tool_result",
            {"id": call.id, "duration_ms": 0, "summary": f"failed: {message}", "evidence": failed},
        )
        return [event], ToolReply(call.id, message, is_error=True)
    run.results.append(result)
    run.asked_about |= _asked_about(call.input)
    payload = {"summary": result.summary, "basis": result.basis, "result": to_jsonable_python(result.data)}
    return _tool_events(call.id, result), ToolReply(call.id, json.dumps(payload, separators=(",", ":")))


async def _converse(
    llm: LLM, question: str, graphs: registry.Graphs, known: list[str], run: _Run, disconnected: Disconnected
) -> AsyncIterator[str | Turn]:
    conversation = llm.conversation(SYSTEM_PROMPT, registry.tool_schemas())
    turn = await conversation.ask(question)
    rounds, retried = 0, False
    while True:
        if turn.tool_calls:
            rounds += 1
            if rounds > settings.agent_max_rounds:
                raise RhizoError(f"stopped after {settings.agent_max_rounds} tool rounds without an answer")
            replies = []
            for call in turn.tool_calls:
                if await disconnected():
                    return
                yield sse("tool_call", {"id": call.id, "name": call.name, "args": call.input})
                events, reply = await _run_tool(call, graphs, run)
                for event in events:
                    yield event
                replies.append(reply)
            turn = await conversation.reply(replies)
            continue
        missing = grounding.ungrounded(turn.text, known, run.allowed)
        if missing and not retried and turn.stop_reason == "end_turn":
            retried = True
            turn = await conversation.ask(GROUNDING_RETRY.format(names=", ".join(missing)))
            continue
        yield turn
        return


async def stream_llm(
    llm_factory: Callable[[], LLM],
    question: str,
    graphs: registry.Graphs,
    known: list[str],
    disconnected: Disconnected,
    fallback: Callable[[], AsyncIterator[str]] | None,
) -> AsyncIterator[str]:
    t0 = perf_counter()
    run = _Run()
    final: Turn | None = None
    try:
        async for item in _converse(llm_factory(), question, graphs, known, run, disconnected):
            if isinstance(item, Turn):
                final = item
            else:
                yield item
    except LLMUnavailable as e:
        log.warning("agent: LLM unavailable (%s)", e)
        yield sse("error", {"message": f"{e}. Answering in scripted mode." if fallback else str(e)})
        if fallback:
            async for event in fallback():
                yield event
        else:
            yield _done("n/a", t0)
        return
    except RhizoError as e:
        yield sse("error", {"message": e.message})
        yield _done("n/a", t0)
        return
    if final is None:
        return

    if final.stop_reason == "refusal":
        yield sse("insufficient_data", {"reason": "The model declined to answer this question."})
        yield _done("n/a", t0)
        return
    missing = grounding.ungrounded(final.text, known, run.allowed)
    text = grounding.strip(final.text, missing) if missing else final.text
    if not run.results:
        yield sse("insufficient_data", {"reason": text.strip() or NO_BASIS})
        yield _done("n/a", t0)
        return
    async for token in _answer(text):
        yield token
    yield _done(worst_basis([r.basis for r in run.results]), t0)
