import logging
from dataclasses import dataclass
from typing import Literal

from falkordb import Graph
from redis.exceptions import ResponseError

from rhizo.graph import queries as Q
from rhizo.graph.client import Row, run

log = logging.getLogger("rhizo.algos")

Algorithm = Literal["falkordb", "degree_fallback"]


@dataclass(frozen=True)
class Scores:
    values: dict[str, float]
    algorithm: Algorithm


@dataclass(frozen=True)
class Communities:
    ids: dict[str, int]
    algorithm: Algorithm


@dataclass(frozen=True)
class Degrees:
    dependents: dict[str, int]
    total: dict[str, int]


def degrees(g: Graph) -> Degrees:
    rows = run(g, "service_degrees", Q.SERVICE_DEGREES)
    return Degrees(
        dependents={name: int(i) for name, i, _ in rows},
        total={name: int(i) + int(o) for name, i, o in rows},
    )


_COMMUNITY_LINKS = ("DEPENDS_ON", "CO_CHANGES_WITH")


def _procedure(g: Graph, name: str, cypher: str, params: dict[str, object] | None = None) -> list[Row] | None:
    try:
        return run(g, name, cypher, params)
    except ResponseError as e:
        log.warning("algorithm %s unavailable, using degree fallback: %s", name, e)
        return None


def _scores(g: Graph, name: str, cypher: str) -> Scores:
    rows = _procedure(g, name, cypher)
    if rows is None:
        return Scores({k: float(v) for k, v in degrees(g).dependents.items()}, "degree_fallback")
    return Scores({node: float(score) for node, score in rows}, "falkordb")


def pagerank(g: Graph) -> Scores:
    return _scores(g, "pagerank", Q.PAGERANK)


def centrality(g: Graph) -> Scores:
    return Scores({k: float(v) for k, v in degrees(g).dependents.items()}, "degree_fallback")


def communities(g: Graph) -> Communities:
    present = {row[0] for row in run(g, "relationship_types", Q.RELATIONSHIP_TYPES)}
    config = {"nodeLabels": ["Service"], "relationshipTypes": [t for t in _COMMUNITY_LINKS if t in present]}
    rows = _procedure(g, "label_propagation", Q.LABEL_PROPAGATION, {"config": config})
    if rows is None:
        return Communities({name: 1 for name in degrees(g).total}, "degree_fallback")
    members: dict[int, list[str]] = {}
    for node, community in rows:
        members.setdefault(int(community), []).append(node)
    ordered = sorted(members.values(), key=lambda names: (-len(names), min(names)))
    return Communities({name: i for i, names in enumerate(ordered, 1) for name in names}, "falkordb")
