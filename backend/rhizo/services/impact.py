from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeVar

from falkordb import Graph

from rhizo.core.timeutil import now_epoch, to_epoch
from rhizo.graph import queries as Q
from rhizo.graph import scoring
from rhizo.graph.client import run
from rhizo.models import (
    Basis,
    BlastRadius,
    BlastRadiusRequest,
    ImpactItem,
    Suspect,
    UpstreamSuspects,
    UpstreamSuspectsRequest,
    WhatIf,
    WhatIfRequest,
)
from rhizo.services.nodes import service_nodes, split_roots

T = TypeVar("T")

SUSPECT_MIN_CONFIDENCE = 0.5
RECENT_COMMIT_WINDOW_S = 14 * 86_400
_ROUND = 3


@dataclass(frozen=True)
class Analysis(Generic[T]):
    data: T
    basis: Basis


@dataclass(frozen=True)
class _Path:
    victim: str
    nodes: list[str]
    confidence: float
    basis: Basis

    @property
    def hops(self) -> int:
        return len(self.nodes) - 1


def _ids(names: list[str], resource_tail: bool) -> list[str]:
    ids = [f"svc:{n}" for n in names]
    if resource_tail:
        ids[-1] = f"res:{names[-1]}"
    return ids


def _traversal_paths(
    topology: Graph, cypher: str, name: str, roots: list[str], params: dict[str, object], resource_tail: bool
) -> list[_Path]:
    if not roots:
        return []
    rows = run(topology, name, cypher, {**params, "names": roots})
    return [
        _Path(victim, _ids(path, resource_tail), conf, scoring.worst_basis(sources))
        for victim, path, sources, conf in rows
    ]


def _fallback_paths(topology: Graph, services: list[str], params: dict[str, object]) -> list[_Path]:
    if not services:
        return []
    degree = run(topology, "depends_on_degree", Q.DEPENDS_ON_DEGREE, {**params, "names": services})
    isolated = [name for name, count in degree if count == 0]
    if not isolated:
        return []
    rows = run(topology, "connectivity_fallback", Q.CONNECTIVITY_FALLBACK, {**params, "names": isolated})
    return [
        _Path(victim, [f"svc:{victim}", f"svc:{root}"], conf, "connectivity_fallback")
        for victim, root, conf in rows
    ]


def _best_per_victim(paths: list[_Path]) -> list[_Path]:
    best: dict[str, _Path] = {}
    for p in paths:
        cur = best.get(p.victim)
        if cur is None or (p.hops, -p.confidence) < (cur.hops, -cur.confidence):
            best[p.victim] = p
    return sorted(best.values(), key=lambda p: (p.hops, -p.confidence, p.victim))


def _impact(
    topology: Graph, roots: list[str], max_hops: int, min_conf: float, as_of: datetime | None
) -> tuple[list[ImpactItem], int, Basis]:
    services, resources = split_roots(topology, roots)
    params: dict[str, object] = {
        "min_conf": min_conf,
        "as_of": to_epoch(as_of) if as_of else None,
        "failed": roots,
    }
    paths = [
        *_traversal_paths(
            topology, Q.blast_radius_services(max_hops), "blast_radius", services, params, resource_tail=False
        ),
        *_traversal_paths(
            topology,
            Q.blast_radius_resources(max_hops),
            "blast_radius_resource",
            resources,
            params,
            resource_tail=True,
        ),
        *_fallback_paths(topology, services, params),
    ]
    best = _best_per_victim(paths)
    nodes = service_nodes(topology, [p.victim for p in best])
    items = [
        ImpactItem(
            service=nodes[p.victim],
            hops=p.hops,
            path=p.nodes,
            path_confidence=round(p.confidence, _ROUND),
            basis=p.basis,
        )
        for p in best
    ]
    risk = scoring.risk_score((_tier(i), i.path_confidence) for i in items)
    return items, risk, scoring.worst_basis([i.basis for i in items])


def _tier(item: ImpactItem) -> int | None:
    tier = item.service.properties.get("tier")
    return tier if isinstance(tier, int) else None


def blast_radius(topology: Graph, req: BlastRadiusRequest) -> Analysis[BlastRadius]:
    items, risk, basis = _impact(topology, [req.service], req.max_hops, req.min_confidence, req.as_of)
    return Analysis(BlastRadius(service=req.service, items=items, risk_score=risk), basis)


def what_if(topology: Graph, req: WhatIfRequest) -> Analysis[WhatIf]:
    failed = list(dict.fromkeys(req.services))
    items, risk, basis = _impact(topology, failed, req.max_hops, SUSPECT_MIN_CONFIDENCE, as_of=None)
    return Analysis(WhatIf(failed=failed, items=items, risk_score=risk), basis)


def _upstream(topology: Graph, name: str, max_hops: int) -> tuple[list[_Path], dict[str, int]]:
    split_roots(topology, [name])
    params = {
        "name": name,
        "min_conf": SUSPECT_MIN_CONFIDENCE,
        "as_of": None,
        "since": now_epoch() - RECENT_COMMIT_WINDOW_S,
    }
    rows = run(topology, "upstream_suspects", Q.upstream_suspects(max_hops), params)
    paths = [
        _Path(suspect, _ids(path, resource_tail=False), conf, scoring.worst_basis(sources))
        for suspect, _, path, sources, conf in rows
    ]
    commits = {suspect: int(n) for suspect, n, *_ in rows}
    return _best_per_victim(paths), commits


def upstream_suspects(topology: Graph, req: UpstreamSuspectsRequest) -> Analysis[UpstreamSuspects]:
    best, commits = _upstream(topology, req.service, req.max_hops)
    nodes = service_nodes(topology, [p.victim for p in best])
    suspects = sorted(
        (
            Suspect(
                service=nodes[p.victim],
                hops=p.hops,
                recent_commits=commits[p.victim],
                score=round(scoring.suspect_score(p.hops, commits[p.victim], p.confidence), _ROUND),
            )
            for p in best
        ),
        key=lambda s: (-s.score, s.hops, s.service.name),
    )
    basis = scoring.worst_basis([p.basis for p in best])
    return Analysis(UpstreamSuspects(service=req.service, suspects=suspects), basis)


def upstream_items(topology: Graph, name: str, max_hops: int = 3) -> list[ImpactItem]:
    best, _ = _upstream(topology, name, max_hops)
    nodes = service_nodes(topology, [p.victim for p in best])
    return [
        ImpactItem(
            service=nodes[p.victim],
            hops=p.hops,
            path=p.nodes,
            path_confidence=round(p.confidence, _ROUND),
            basis=p.basis,
        )
        for p in best
    ]
