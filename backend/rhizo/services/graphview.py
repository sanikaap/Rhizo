from collections import deque
from dataclasses import dataclass
from datetime import datetime

from falkordb import Graph

from rhizo.core.errors import NotFound
from rhizo.core.timeutil import to_epoch, to_iso
from rhizo.graph import queries as Q
from rhizo.graph.client import Row, run, scalar
from rhizo.graph.version import VersionedCache
from rhizo.models import (
    BlastRadiusRequest,
    GraphCounts,
    GraphData,
    GraphEdge,
    GraphNode,
    Provenance,
    ServiceDetail,
)
from rhizo.services import impact, rankings, responders
from rhizo.services.nodes import engineer_node, nodes_from_service_rows, resource_node

_ID_PREFIX = {"Service": "svc", "Resource": "res"}


@dataclass(frozen=True)
class _Edge:
    edge: GraphEdge
    valid_from: int | None
    valid_to: int | None

    def valid_at(self, as_of: int | None) -> bool:
        if as_of is None:
            return self.valid_to is None
        return (self.valid_from is None or self.valid_from <= as_of) and (
            self.valid_to is None or self.valid_to > as_of
        )


@dataclass(frozen=True)
class Snapshot:
    nodes: list[GraphNode]
    edges: list[_Edge]


_snapshots: VersionedCache[Snapshot] = VersionedCache()


def graph_counts(topology: Graph, memory: Graph) -> GraphCounts:
    return GraphCounts(
        services=scalar(topology, "count_services", Q.COUNT_SERVICES) or 0,
        edges=scalar(topology, "count_live_edges", Q.COUNT_LIVE_EDGES) or 0,
        incidents=scalar(memory, "count_incidents", Q.COUNT_INCIDENTS) or 0,
    )


def _edge(row: Row) -> _Edge:
    rel, a_label, a_name, b_label, b_name, source, conf, valid_from, valid_to, evidence = row
    source_id = f"{_ID_PREFIX[str(a_label)]}:{a_name}"
    target_id = f"{_ID_PREFIX[str(b_label)]}:{b_name}"
    vf = int(valid_from) if isinstance(valid_from, int | float) else None
    vt = int(valid_to) if isinstance(valid_to, int | float) else None
    return _Edge(
        edge=GraphEdge(
            id=f"{rel}:{source_id}->{target_id}",
            source_id=source_id,
            target_id=target_id,
            type=rel,
            provenance=source,
            confidence=float(conf),
            valid_from=to_iso(vf),
            valid_to=to_iso(vt),
            evidence=evidence if isinstance(evidence, str) else None,
        ),
        valid_from=vf,
        valid_to=vt,
    )


def _load_snapshot(topology: Graph) -> Snapshot:
    services = nodes_from_service_rows(run(topology, "snapshot_services", Q.SERVICE_NODES, {"names": None}))
    resources = [resource_node(*row) for row in run(topology, "snapshot_resources", Q.RESOURCE_NODES)]
    edges = [_edge(row) for row in run(topology, "snapshot_edges", Q.GRAPH_EDGES)]
    return Snapshot(nodes=[*services.values(), *resources], edges=edges)


def snapshot(topology: Graph) -> Snapshot:
    return _snapshots.get(topology, "snapshot", lambda: _load_snapshot(topology))


def _with_risk(topology: Graph, nodes: list[GraphNode]) -> list[GraphNode]:
    risk = rankings.risk_scores(topology)
    return [n.model_copy(update={"risk_score": risk[n.name]}) if n.name in risk else n for n in nodes]


def _neighbourhood(center: str, edges: list[GraphEdge], depth: int) -> set[str]:
    adjacent: dict[str, set[str]] = {}
    for e in edges:
        adjacent.setdefault(e.source_id, set()).add(e.target_id)
        adjacent.setdefault(e.target_id, set()).add(e.source_id)
    keep, frontier = {center}, deque([(center, 0)])
    while frontier:
        node, d = frontier.popleft()
        if d == depth:
            continue
        for nxt in adjacent.get(node, ()):
            if nxt not in keep:
                keep.add(nxt)
                frontier.append((nxt, d + 1))
    return keep


def graph(
    topology: Graph,
    center: str | None,
    depth: int,
    min_confidence: float,
    provenance: list[Provenance] | None,
    as_of: datetime | None,
) -> GraphData:
    snap = snapshot(topology)
    at = to_epoch(as_of) if as_of else None
    edges = [
        e.edge
        for e in snap.edges
        if e.valid_at(at)
        and e.edge.confidence >= min_confidence
        and (not provenance or e.edge.provenance in provenance)
    ]
    nodes = snap.nodes
    if center is not None:
        center_id = next((n.id for n in nodes if n.name == center), None)
        if center_id is None:
            raise NotFound(f"no service or resource named {center}")
        keep = _neighbourhood(center_id, edges, depth)
        nodes = [n for n in nodes if n.id in keep]
        edges = [e for e in edges if e.source_id in keep and e.target_id in keep]
    return GraphData(nodes=_with_risk(topology, nodes), edges=edges)


def services(topology: Graph) -> list[GraphNode]:
    return _with_risk(topology, [n for n in snapshot(topology).nodes if n.label == "Service"])


OWNERS_SHOWN = 3


def _owners(topology: Graph, name: str) -> list[GraphNode]:
    rows = run(topology, "service_owners", Q.SERVICE_OWNERS, {"name": name, "limit": OWNERS_SHOWN})
    return [
        engineer_node(handle, display, pseudonymous, commits)
        for handle, display, commits, pseudonymous in rows
    ]


def service_detail(topology: Graph, memory: Graph, name: str) -> ServiceDetail:
    snap = snapshot(topology)
    node = next((n for n in snap.nodes if n.name == name and n.label == "Service"), None)
    if node is None:
        raise NotFound(f"service {name} not found")
    live = [e.edge for e in snap.edges if e.valid_at(None)]
    resource_ids = {e.target_id for e in live if e.type == "USES" and e.source_id == node.id}
    return ServiceDetail(
        node=node,
        owners=_owners(topology, name),
        upstream=impact.upstream_items(topology, name),
        blast_radius_count=len(impact.blast_radius(topology, BlastRadiusRequest(service=name)).data.items),
        responders=responders.recommend(topology, memory, [name]),
        resources=[n for n in snap.nodes if n.id in resource_ids],
    )
