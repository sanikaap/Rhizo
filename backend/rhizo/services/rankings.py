from falkordb import Graph

from rhizo.graph import algos
from rhizo.graph.version import VersionedCache
from rhizo.models import RankingItem, RankingMetric, Rankings
from rhizo.services.nodes import service_nodes

_ROUND = 3
_full: VersionedCache[Rankings] = VersionedCache()


def _normalise(values: dict[str, float]) -> dict[str, float]:
    top = max(values.values(), default=0.0)
    return {k: round(v / top, _ROUND) if top > 0 else 0.0 for k, v in values.items()}


def _compute(topology: Graph, metric: RankingMetric) -> Rankings:
    community: dict[str, int] = {}
    if metric == "community":
        groups = algos.communities(topology)
        community, algorithm = groups.ids, groups.algorithm
        raw = {k: float(v) for k, v in algos.degrees(topology).total.items()}
    else:
        scores = algos.pagerank(topology) if metric == "pagerank" else algos.centrality(topology)
        raw, algorithm = scores.values, scores.algorithm
    scored = _normalise(raw)
    nodes = service_nodes(topology, list(scored))
    items = [
        RankingItem(service=nodes[name], score=score, community=community.get(name))
        for name, score in sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))
        if name in nodes
    ]
    return Rankings(metric=metric, algorithm=algorithm, items=items)


def rank(topology: Graph, metric: RankingMetric, top_k: int) -> Rankings:
    full = _full.get(topology, f"rankings:{metric}", lambda: _compute(topology, metric))
    return full.model_copy(update={"items": full.items[:top_k]})


def risk_scores(topology: Graph) -> dict[str, int]:
    full = _full.get(topology, "rankings:pagerank", lambda: _compute(topology, "pagerank"))
    return {item.service.name: round(item.score * 100) for item in full.items}
