import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from rhizo.agent.grounding import find_mentions
from rhizo.agent.registry import ToolResult
from rhizo.models import (
    BlastRadius,
    HiddenDependency,
    Rankings,
    Responder,
    SimilarIncident,
    UpstreamSuspects,
)

_HIDDEN = re.compile(r"hidden|undeclared|coupl|nobody declared")
_CRITICAL = re.compile(r"critical|important|pagerank|central|single point")
_ROOT_CAUSE = re.compile(r"why|root cause|suspect|slow|errors?|5xx|latency|caus")


@dataclass(frozen=True)
class Step:
    tool: str
    args: Callable[[list[ToolResult]], dict[str, Any]]


@dataclass(frozen=True)
class Plan:
    steps: list[Step]
    answer: Callable[[list[ToolResult]], str]


@dataclass(frozen=True)
class Insufficient:
    reason: str


def _list(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else f"{', '.join(xs[:-1])} and {xs[-1]}"


def _s(n: int, one: str = "", many: str = "s") -> str:
    return one if n == 1 else many


def mentioned(question: str, names: list[str]) -> str | None:
    hits = find_mentions(question, names)
    return hits[0][1] if hits else None


def _hidden_answer(target: str | None) -> Callable[[list[ToolResult]], str]:
    def answer(results: list[ToolResult]) -> str:
        found: list[HiddenDependency] = results[0].data
        scope = f" involving {target}" if target else ""
        if not found:
            return f"No hidden dependencies found{scope}."
        lines = [
            f"I found **{len(found)} undeclared dependenc{_s(len(found), 'y', 'ies')}**{scope}. "
            "These are *inferred*, not declared in any manifest:\n",
            *(f"- **{h.a.name} ↔ {h.b.name}**: {h.evidence} (confidence {h.confidence:.2f})" for h in found),
        ]
        return "\n".join(lines)

    return answer


def _critical_answer(results: list[ToolResult]) -> str:
    r: Rankings = results[0].data
    how = (
        "By PageRank over DEPENDS_ON edges"
        if r.algorithm == "falkordb"
        else "By number of live dependents (PageRank unavailable, degree fallback)"
    )
    return "\n".join(
        [
            f"{how}, the most depended-upon services are:\n",
            *(
                f"{k}. **{i.service.name}** (score {i.score:.2f}, tier {i.service.properties.get('tier')})"
                for k, i in enumerate(r.items, 1)
            ),
        ]
    )


def _root_cause_answer(target: str) -> Callable[[list[ToolResult]], str]:
    def answer(results: list[ToolResult]) -> str:
        up: UpstreamSuspects = results[0].data
        similar: list[SimilarIncident] = results[1].data
        top = up.suspects[:3]
        if top:
            first = top[0]
            commits = (
                f" with {first.recent_commits} commit(s) in the last 14 days" if first.recent_commits else ""
            )
            lines = [
                f"The most likely upstream cause for **{target}** is **{first.service.name}**: it is "
                f"{first.hops} hop{_s(first.hops)} away{commits}.\n",
                *(
                    f"- {s.service.name}: {s.hops} hop(s), {s.recent_commits} recent commits, "
                    f"score {s.score:.2f}"
                    for s in top
                ),
            ]
        else:
            lines = [
                f"**{target}** has no upstream dependencies in the graph, so the fault is likely inside it."
            ]
        if similar:
            inc = similar[0].incident
            lines.append(
                f"\nSimilar past incident: **{inc.id}** “{inc.title}”. Fix then: {inc.fix or 'not recorded'}"
            )
        return "\n".join(lines)

    return answer


def _blast_answer(target: str) -> Callable[[list[ToolResult]], str]:
    def answer(results: list[ToolResult]) -> str:
        br: BlastRadius = results[0].data
        page: list[Responder] = results[1].data
        if not br.items:
            lines = [
                f"Nothing in the graph depends on **{target}**, so its failure has no downstream "
                "blast radius. (Upstream services it relies on are a separate question.)"
            ]
        else:
            n = len(br.items)
            lines = [
                f"If **{target}** fails, **{n} service{_s(n)}** break{_s(n, 's', '')}: "
                f"{_list([i.service.name for i in br.items])}. Risk score **{br.risk_score}/100**.\n",
                *(
                    f"- {i.service.name}: {i.hops} hop{_s(i.hops)}, "
                    f"path confidence {i.path_confidence:.2f} ({i.basis})"
                    for i in br.items[:4]
                ),
            ]
        if page:
            r = page[0]
            lines.append(
                f"\nPage **{r.engineer.name}** (@{r.engineer.properties.get('handle')}): {r.reason}."
            )
        return "\n".join(lines)

    return answer


def plan(
    question: str, context_service: str | None, names: list[str], services: list[str]
) -> Plan | Insufficient:
    q = question.lower()
    target = mentioned(question, names) or (context_service if context_service in names else None)

    if _HIDDEN.search(q):
        return Plan(
            [Step("find_hidden_dependencies", lambda _: {"service": target})],
            _hidden_answer(target),
        )
    if _CRITICAL.search(q):
        return Plan(
            [Step("rank_criticality", lambda _: {"metric": "pagerank", "top_k": 5})], _critical_answer
        )
    if target and _ROOT_CAUSE.search(q):
        return Plan(
            [
                Step("get_upstream_suspects", lambda _: {"service": target, "max_hops": 3}),
                Step("find_similar_incidents", lambda _: {"services": [target], "top_k": 3}),
            ],
            _root_cause_answer(target),
        )
    if target:

        def responder_args(results: list[ToolResult]) -> dict[str, Any]:
            victims = [i.service.name for i in results[0].data.items[:2]]
            return {"services": [target, *victims], "top_k": 3}

        return Plan(
            [
                Step("get_blast_radius", lambda _: {"service": target, "max_hops": 4, "min_confidence": 0.5}),
                Step("recommend_responders", responder_args),
            ],
            _blast_answer(target),
        )
    return Insufficient(
        "The question does not name a service or resource that exists in the graph. "
        f"Try one of: {', '.join(services[:4])}."
    )
