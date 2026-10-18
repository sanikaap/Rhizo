from falkordb import Graph

from rhizo.core.errors import BadRequest, NotFound
from rhizo.core.timeutil import now_epoch, to_epoch, to_iso
from rhizo.graph import queries as Q
from rhizo.graph import scoring, version
from rhizo.graph.client import Row, run, run_write, scalar
from rhizo.models import (
    EdgeRef,
    GraphUpdates,
    Incident,
    IncidentDetail,
    NewIncident,
    ResolveIncident,
    ResolveResult,
    SimilarIncident,
    SuggestedEdge,
)
from rhizo.services.hidden import find_hidden
from rhizo.services.nodes import require_services, split_roots

SIMILARITY_THRESHOLD = 0.2
_ROUND = 2


def root_cause_rows(topology: Graph, pairs: list[tuple[str, str]]) -> tuple[list[dict[str, str]], ...]:
    services, resources = split_roots(topology, sorted({name for _, name in pairs}))
    as_rows = [{"id": i, "name": n} for i, n in pairs]
    return [r for r in as_rows if r["name"] in services], [r for r in as_rows if r["name"] in resources]


def _incident(row: Row) -> Incident:
    (
        iid,
        title,
        symptom,
        severity,
        status,
        started,
        resolved,
        affected,
        root_cause,
        fix,
        by,
        source,
        url,
    ) = row
    return Incident(
        id=iid,
        title=title,
        symptom=symptom,
        severity=severity,
        status=status,
        started_at=to_iso(started) or "",
        resolved_at=to_iso(resolved),
        affected=sorted(affected),
        root_cause=root_cause,
        fix=fix,
        resolved_by=by,
        source=source,
        url=url,
    )


def list_incidents(memory: Graph, ids: list[str] | None = None) -> list[Incident]:
    return [_incident(row) for row in run(memory, "incidents", Q.INCIDENTS, {"ids": ids})]


def _get(memory: Graph, incident_id: str) -> Incident:
    found = list_incidents(memory, [incident_id])
    if not found:
        raise NotFound(f"incident {incident_id} not found")
    return found[0]


def find_similar(
    memory: Graph, names: list[str], top_k: int = 3, exclude: str | None = None
) -> list[SimilarIncident]:
    wanted = sorted(set(names))
    if not wanted:
        return []
    rows = run(memory, "similar_incidents", Q.SIMILAR_INCIDENTS, {"names": wanted, "exclude": exclude})
    scored = {iid: round(overlap / (len(wanted) + total - overlap), _ROUND) for iid, overlap, total in rows}
    top = sorted(
        ((iid, s) for iid, s in scored.items() if s > SIMILARITY_THRESHOLD), key=lambda kv: (-kv[1], kv[0])
    )[:top_k]
    incidents = {i.id: i for i in list_incidents(memory, [iid for iid, _ in top])}
    return [SimilarIncident(incident=incidents[iid], similarity=s) for iid, s in top if iid in incidents]


def _suggested_edges(topology: Graph, affected: list[str]) -> list[SuggestedEdge]:
    involved = set(affected)
    return [
        SuggestedEdge(
            from_=h.a.name,
            to=h.b.name,
            type="DEPENDS_ON",
            reason=f"Shared {h.via.name}" if h.via else f"Co-change, Jaccard {h.jaccard or 0:.2f}",
        )
        for h in find_hidden(topology)
        if h.a.name in involved or h.b.name in involved
    ]


def detail(topology: Graph, memory: Graph, incident_id: str) -> IncidentDetail:
    inc = _get(memory, incident_id)
    return IncidentDetail(
        incident=inc,
        similar=find_similar(memory, inc.affected, exclude=inc.id),
        suggested_edges=_suggested_edges(topology, inc.affected),
    )


def create(topology: Graph, memory: Graph, body: NewIncident) -> Incident:
    require_services(topology, body.affected, "affected")
    started = to_epoch(body.started_at) if body.started_at else now_epoch()
    params = {
        "title": body.title,
        "symptom": body.symptom,
        "severity": body.severity,
        "started_at": started,
        "affected": sorted(set(body.affected)),
    }
    incident_id = scalar(memory, "create_incident", Q.CREATE_INCIDENT, params)
    return _get(memory, incident_id)


def _validate_resolution(topology: Graph, body: ResolveIncident) -> None:
    try:
        split_roots(topology, [body.root_cause])
    except NotFound as e:
        raise BadRequest(f"root_cause: {e.message}") from e
    if body.resolved_by and not scalar(
        topology, "engineer_exists", Q.ENGINEER_EXISTS, {"handle": body.resolved_by}
    ):
        raise BadRequest(f"resolved_by: no engineer with handle {body.resolved_by}")
    edges = [*body.confirmed_edges, *body.refuted_edges]
    if any(e.from_ == e.to for e in edges):
        raise BadRequest("an edge cannot point at its own service")
    if edges:
        require_services(topology, [n for e in edges for n in (e.from_, e.to)], "edge endpoints")


def _edge_rows(edges: list[EdgeRef]) -> list[dict[str, str]]:
    return [{"from": e.from_, "to": e.to} for e in edges]


def resolve(topology: Graph, memory: Graph, incident_id: str, body: ResolveIncident) -> ResolveResult:
    _get(memory, incident_id)
    _validate_resolution(topology, body)
    now = now_epoch()
    confirmed, refuted = _edge_rows(body.confirmed_edges), _edge_rows(body.refuted_edges)

    run(
        memory,
        "set_resolved",
        Q.SET_RESOLVED,
        {"id": incident_id, "now": now, "root_cause": body.root_cause, "fix": body.fix},
    )
    service_rc, resource_rc = root_cause_rows(topology, [(incident_id, body.root_cause)])
    for name, cypher, rows in (
        ("set_root_cause_service", Q.SET_ROOT_CAUSE_SERVICE, service_rc),
        ("set_root_cause_resource", Q.SET_ROOT_CAUSE_RESOURCE, resource_rc),
    ):
        if rows:
            run(memory, name, cypher, {"rows": rows})
    if body.resolved_by:
        run(
            memory,
            "set_resolved_by",
            Q.SET_RESOLVED_BY,
            {"rows": [{"id": incident_id, "handle": body.resolved_by}]},
        )
    if confirmed:
        run(memory, "record_revealed", Q.RECORD_REVEALED, {"id": incident_id, "rows": confirmed})

    created = strengthened = weakened = 0
    if confirmed:
        res = run_write(
            topology,
            "write_back_confirmed",
            Q.WRITE_BACK_CONFIRMED,
            {
                "rows": confirmed,
                "incident_id": incident_id,
                "now": now,
                "created_conf": scoring.INCIDENT_CONFIDENCE,
                "step": scoring.CONFIRM_STEP,
            },
        )
        created = res.relationships_created
        strengthened = int(res.rows[0][0]) - created
    if refuted:
        weakened = int(
            scalar(
                topology,
                "refute_edges",
                Q.REFUTE_EDGES,
                {"rows": refuted, "step": scoring.REFUTE_STEP, "floor": scoring.REFUTE_FLOOR},
            )
            or 0
        )
    if confirmed or refuted:
        version.bump(topology, now)

    return ResolveResult(
        incident=_get(memory, incident_id),
        graph_updates=GraphUpdates(created=created, strengthened=strengthened, weakened=weakened),
    )
