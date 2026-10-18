import math
from collections import defaultdict

from falkordb import Graph

from rhizo.core.timeutil import now_epoch
from rhizo.graph import queries as Q
from rhizo.graph.client import run
from rhizo.models import GraphNode, Responder
from rhizo.services.nodes import engineer_node

COMMIT_WEIGHT, RESOLUTION_WEIGHT = 0.6, 0.4
COMMIT_DECAY_DAYS = 90
_DAY_S = 86_400


def engineer_nodes(topology: Graph, handles: list[str]) -> dict[str, GraphNode]:
    rows = run(topology, "engineer_nodes", Q.ENGINEER_NODES, {"handles": sorted(set(handles))})
    return {handle: engineer_node(handle, name, pseudonymous) for handle, name, pseudonymous in rows}


def _reason(services: set[str], resolutions: int) -> str:
    parts = []
    if services:
        parts.append(f"Recent commits to {', '.join(sorted(services))}")
    if resolutions:
        parts.append(f"resolved {resolutions} related incident{'s' if resolutions > 1 else ''}")
    return "; ".join(parts)


def recommend(topology: Graph, memory: Graph, names: list[str], top_k: int = 3) -> list[Responder]:
    if not names:
        return []
    now = now_epoch()
    commit_score: dict[str, float] = defaultdict(float)
    touched: dict[str, set[str]] = defaultdict(set)
    for handle, service, count, last_at in run(
        topology, "responder_commits", Q.RESPONDER_COMMITS, {"names": names}
    ):
        days = max(0.0, (now - int(last_at)) / _DAY_S)
        commit_score[handle] += int(count) * math.exp(-days / COMMIT_DECAY_DAYS)
        touched[handle].add(service)
    resolutions = {
        handle: int(n)
        for handle, n in run(memory, "responder_resolutions", Q.RESPONDER_RESOLUTIONS, {"names": names})
    }

    candidates = set(commit_score) | set(resolutions)
    nodes = engineer_nodes(topology, list(candidates))
    best_commit = max(commit_score.values(), default=0.0) or 1.0
    best_res = max(resolutions.values(), default=0) or 1
    ranked = sorted(
        (
            Responder(
                engineer=nodes[h],
                score=round(
                    COMMIT_WEIGHT * commit_score.get(h, 0.0) / best_commit
                    + RESOLUTION_WEIGHT * resolutions.get(h, 0) / best_res,
                    2,
                ),
                reason=_reason(touched.get(h, set()), resolutions.get(h, 0)),
            )
            for h in candidates
            if h in nodes
        ),
        key=lambda r: (-r.score, r.engineer.id),
    )
    return ranked[:top_k]
