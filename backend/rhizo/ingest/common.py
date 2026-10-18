from dataclasses import dataclass
from typing import Any

from falkordb import Graph

from rhizo.graph.client import run, run_write


@dataclass(frozen=True)
class IngestCounts:
    nodes_created: int = 0
    edges_created: int = 0
    edges_updated: int = 0
    edges_expired: int = 0

    def __add__(self, other: "IngestCounts") -> "IngestCounts":
        return IngestCounts(
            nodes_created=self.nodes_created + other.nodes_created,
            edges_created=self.edges_created + other.edges_created,
            edges_updated=self.edges_updated + other.edges_updated,
            edges_expired=self.edges_expired + other.edges_expired,
        )


BATCH_ROWS = 2000


def _batches(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    return [rows[i : i + BATCH_ROWS] for i in range(0, len(rows), BATCH_ROWS)]


def write_nodes(g: Graph, name: str, cypher: str, rows: list[dict[str, Any]], **params: Any) -> IngestCounts:
    total = IngestCounts()
    for batch in _batches(rows):
        res = run_write(g, name, cypher, {"rows": batch, **params})
        total += IngestCounts(nodes_created=res.nodes_created)
    return total


def write(g: Graph, name: str, cypher: str, rows: list[dict[str, Any]], **params: Any) -> IngestCounts:
    total = IngestCounts()
    for batch in _batches(rows):
        res = run_write(g, name, cypher, {"rows": batch, **params})
        total += IngestCounts(nodes_created=res.nodes_created, edges_created=res.relationships_created)
    return total


def write_edges(g: Graph, name: str, cypher: str, rows: list[dict[str, Any]], **params: Any) -> IngestCounts:
    total = IngestCounts()
    for batch in _batches(rows):
        res = run_write(g, name, cypher, {"rows": batch, **params})
        touched = int(res.rows[0][0]) if res.rows else 0
        total += IngestCounts(
            edges_created=res.relationships_created, edges_updated=touched - res.relationships_created
        )
    return total


def expire_edges(g: Graph, name: str, cypher: str, **params: Any) -> IngestCounts:
    rows = run(g, name, cypher, params)
    return IngestCounts(edges_expired=int(rows[0][0]) if rows else 0)
