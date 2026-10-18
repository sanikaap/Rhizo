from collections.abc import AsyncIterator

import anyio
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from rhizo.agent import loop, scripted
from rhizo.agent.llm import default_llm
from rhizo.agent.registry import Graphs
from rhizo.api.deps import Client
from rhizo.config import settings
from rhizo.graph.client import GraphClient
from rhizo.models import AskRequest
from rhizo.services import graphview

router = APIRouter(tags=["agent"])

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _prepare(client: GraphClient) -> tuple[Graphs, list[str], list[str]]:
    graphs = Graphs(topology=client.topology(), memory=client.memory())
    nodes = graphview.snapshot(graphs.topology).nodes
    return graphs, [n.name for n in nodes], [n.name for n in nodes if n.label == "Service"]


@router.post("/agent/ask")
async def ask(body: AskRequest, request: Request, client: Client) -> StreamingResponse:
    graphs, names, services = await anyio.to_thread.run_sync(_prepare, client)
    context_service = body.context.service if body.context else None

    def scripted_stream() -> AsyncIterator[str]:
        plan = scripted.plan(body.question, context_service, names, services)
        return loop.stream_scripted(plan, graphs, request.is_disconnected)

    if settings.agent_mode == "scripted":
        events = scripted_stream()
    else:
        question = body.question
        if context_service:
            question += f"\n\n(The user is looking at {context_service} in the graph.)"
        events = loop.stream_llm(
            default_llm,
            question,
            graphs,
            names,
            request.is_disconnected,
            fallback=scripted_stream if settings.agent_fallback == "scripted" else None,
        )
    return StreamingResponse(events, media_type="text/event-stream", headers=_SSE_HEADERS)
