from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from time import perf_counter
from typing import Any

from falkordb import Graph
from pydantic import BaseModel, Field

from rhizo.core import querylog
from rhizo.core.errors import BadRequest
from rhizo.core.validate import MAX_TOP_K, Name
from rhizo.models import (
    Basis,
    BlastRadius,
    BlastRadiusRequest,
    Evidence,
    GraphPath,
    HiddenDependency,
    RankingMetric,
    Rankings,
    Responder,
    SimilarIncident,
    UpstreamSuspects,
    UpstreamSuspectsRequest,
)
from rhizo.services import impact, incidents, rankings, responders
from rhizo.services.hidden import find_hidden


@dataclass(frozen=True)
class Graphs:
    topology: Graph
    memory: Graph


class HiddenArgs(BaseModel):
    service: Name | None = None


class RankArgs(BaseModel):
    metric: RankingMetric = "pagerank"
    top_k: int = Field(default=10, ge=1, le=MAX_TOP_K)


class ServicesArgs(BaseModel):
    services: list[Name] = Field(min_length=1, max_length=20)
    top_k: int = Field(default=3, ge=1, le=MAX_TOP_K)


@dataclass(frozen=True)
class Outcome:
    data: Any
    summary: str
    returned_ids: list[str]
    basis: Basis = "n/a"
    highlight: GraphPath | None = None
    note: str | None = None


@dataclass(frozen=True)
class ToolResult:
    data: Any
    summary: str
    evidence: Evidence
    basis: Basis
    highlight: GraphPath | None
    duration_ms: int


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    run: Callable[[Graphs, Any], Outcome]


def edge_ids_from_paths(paths: list[list[str]]) -> list[str]:
    seen: dict[str, None] = {}
    for path in paths:
        for a, b in pairwise(path):
            seen[f"{'USES' if b.startswith('res:') else 'DEPENDS_ON'}:{a}->{b}"] = None
    return list(seen)


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def _blast(g: Graphs, args: BlastRadiusRequest) -> Outcome:
    result = impact.blast_radius(g.topology, args)
    br: BlastRadius = result.data
    paths = [i.path for i in br.items]
    failing = paths[0][-1] if paths else None
    return Outcome(
        data=br,
        summary=f"{len(br.items)} {_plural(len(br.items), 'victim', 'victims')}, risk {br.risk_score}",
        returned_ids=[i.service.id for i in br.items],
        basis=result.basis,
        highlight=GraphPath(
            node_ids=[*([failing] if failing else []), *(i.service.id for i in br.items)],
            edge_ids=edge_ids_from_paths(paths),
            paths=paths,
        ),
        note="Failing node is a Resource: first hop follows USES edges into it."
        if failing and failing.startswith("res:")
        else None,
    )


def _upstream(g: Graphs, args: UpstreamSuspectsRequest) -> Outcome:
    result = impact.upstream_suspects(g.topology, args)
    up: UpstreamSuspects = result.data
    top = up.suspects[:3]
    origin = f"svc:{args.service}"
    return Outcome(
        data=up,
        summary=f"{len(up.suspects)} upstream {_plural(len(up.suspects), 'suspect', 'suspects')}",
        returned_ids=[s.service.id for s in up.suspects],
        basis=result.basis,
        highlight=GraphPath(
            node_ids=[origin, *(s.service.id for s in top)],
            edge_ids=[f"DEPENDS_ON:{origin}->{s.service.id}" for s in top if s.hops == 1],
            paths=[],
        ),
    )


def _hidden(g: Graphs, args: HiddenArgs) -> Outcome:
    found: list[HiddenDependency] = find_hidden(g.topology, args.service)
    paths = [[h.a.id, *([h.via.id] if h.via else []), h.b.id] for h in found]
    return Outcome(
        data=found,
        summary=f"{len(found)} hidden {_plural(len(found), 'dependency', 'dependencies')}",
        returned_ids=[i for h in found for i in (h.a.id, h.b.id, *([h.via.id] if h.via else []))],
        basis="inferred" if found else "n/a",
        highlight=GraphPath(
            node_ids=list(dict.fromkeys(i for p in paths for i in p)), edge_ids=[], paths=paths
        ),
    )


def _rank(g: Graphs, args: RankArgs) -> Outcome:
    r: Rankings = rankings.rank(g.topology, args.metric, args.top_k)
    label = (
        "PageRank"
        if r.algorithm == "falkordb" and args.metric == "pagerank"
        else f"{args.metric} ({r.algorithm})"
    )
    return Outcome(
        data=r,
        summary=f"Top {len(r.items)} by {label}",
        returned_ids=[i.service.id for i in r.items],
        note="Degree fallback: the FalkorDB procedure was not used."
        if r.algorithm == "degree_fallback"
        else None,
    )


def _responders(g: Graphs, args: ServicesArgs) -> Outcome:
    found: list[Responder] = responders.recommend(g.topology, g.memory, args.services, args.top_k)
    return Outcome(
        data=found,
        summary=f"{len(found)} {_plural(len(found), 'responder', 'responders')}",
        returned_ids=[r.engineer.id for r in found],
    )


def _similar(g: Graphs, args: ServicesArgs) -> Outcome:
    found: list[SimilarIncident] = incidents.find_similar(g.memory, args.services, args.top_k)
    return Outcome(
        data=found,
        summary=f"{len(found)} similar past {_plural(len(found), 'incident', 'incidents')}",
        returned_ids=[f"inc:{s.incident.id}" for s in found],
    )


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool(
            "get_blast_radius",
            "Services that break if a service or resource fails.",
            BlastRadiusRequest,
            _blast,
        ),
        Tool(
            "get_upstream_suspects",
            "What a failing service depends on, ranked as likely root causes.",
            UpstreamSuspectsRequest,
            _upstream,
        ),
        Tool("find_hidden_dependencies", "Coupling no manifest declares.", HiddenArgs, _hidden),
        Tool("rank_criticality", "Most depended-upon services.", RankArgs, _rank),
        Tool("recommend_responders", "Engineers to page for a set of services.", ServicesArgs, _responders),
        Tool(
            "find_similar_incidents",
            "Past incidents that affected the same services.",
            ServicesArgs,
            _similar,
        ),
    )
}


def tool_schemas() -> list[dict[str, Any]]:
    return [
        {"name": t.name, "description": t.description, "input_schema": t.args_model.model_json_schema()}
        for t in TOOLS.values()
    ]


def call(name: str, graphs: Graphs, raw_args: dict[str, Any]) -> ToolResult:
    tool = TOOLS.get(name)
    if tool is None:
        raise BadRequest(f"unknown tool {name}")
    args = tool.args_model.model_validate(raw_args)
    t0 = perf_counter()
    with querylog.scope() as qs:
        out = tool.run(graphs, args)
    return ToolResult(
        data=out.data,
        summary=out.summary,
        evidence=Evidence(
            cypher=qs.cypher,
            params=args.model_dump(mode="json", exclude_none=True),
            returned_ids=out.returned_ids,
            note=out.note,
        ),
        basis=out.basis,
        highlight=out.highlight,
        duration_ms=round((perf_counter() - t0) * 1000),
    )
