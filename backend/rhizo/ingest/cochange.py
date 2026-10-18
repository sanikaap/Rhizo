from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from falkordb import Graph

from rhizo.graph import queries as Q
from rhizo.graph.client import run
from rhizo.graph.scoring import cochange_confidence
from rhizo.ingest.common import IngestCounts, expire_edges, write_edges


@dataclass(frozen=True)
class Thresholds:
    min_support: int
    min_jaccard: float
    max_files_per_commit: int
    max_services_per_commit: int


@dataclass(frozen=True)
class Pair:
    a: str
    b: str
    support: int
    jaccard: float


def mine(service_sets: list[set[str]], t: Thresholds) -> list[Pair]:
    eligible = [s for s in service_sets if 0 < len(s) <= t.max_services_per_commit]
    per_service = Counter(name for s in eligible for name in s)
    support = Counter(pair for s in eligible for pair in combinations(sorted(s), 2))
    pairs = []
    for (a, b), n in sorted(support.items()):
        jaccard = n / (per_service[a] + per_service[b] - n)
        if n >= t.min_support and jaccard >= t.min_jaccard:
            pairs.append(Pair(a, b, n, round(jaccard, 3)))
    return pairs


def ingest(topology: Graph, now: int, t: Thresholds) -> IngestCounts:
    rows = run(topology, "commit_services", Q.COMMIT_SERVICES, {"max_files": t.max_files_per_commit})
    pairs = mine([set(services) for _, services in rows], t)
    edge_rows: list[dict[str, Any]] = [
        {
            "source": p.a,
            "target": p.b,
            "support": p.support,
            "jaccard": p.jaccard,
            "confidence": round(cochange_confidence(p.jaccard), 3),
            "evidence": f"co-changed in {p.support} commits (jaccard {p.jaccard:.2f})",
        }
        for p in pairs
    ]
    return write_edges(topology, "cochange_upsert", Q.UPSERT_CO_CHANGE, edge_rows, now=now) + expire_edges(
        topology, "cochange_expire", Q.EXPIRE_CO_CHANGE, seen=[f"{p.a}->{p.b}" for p in pairs], now=now
    )
