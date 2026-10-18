from falkordb import Graph

from rhizo.config import settings
from rhizo.core.errors import BadRequest
from rhizo.graph import queries as Q
from rhizo.graph.client import run
from rhizo.models import Basis, ChangeCheck, ChangeCheckRequest, CoupledFile, ImpactItem, WhatIfRequest
from rhizo.services import impact, incidents, responders
from rhizo.services.impact import Analysis
from rhizo.services.nodes import require_services, service_nodes

COUPLED_FILES_LIMIT = 5


def services_for_files(topology: Graph, files: list[str]) -> set[str]:
    prefixes = run(topology, "service_prefixes", Q.SERVICE_PREFIXES)
    owners = set()
    for path in files:
        matches = [(len(prefix), name) for name, prefix in prefixes if path.startswith(prefix)]
        if matches:
            owners.add(max(matches)[1])
    return owners


def _coupled_files(topology: Graph, files: list[str], services: list[str]) -> list[CoupledFile]:
    sources = files or [
        row[0] for row in run(topology, "service_files", Q.SERVICE_FILES, {"names": services})
    ]
    if not sources:
        return []
    rows = run(
        topology,
        "coupled_files",
        Q.COUPLED_FILES,
        {"paths": sources, "max_files": settings.cochange_max_files_per_commit, "limit": COUPLED_FILES_LIMIT},
    )
    return [CoupledFile(path=path, count=int(n)) for path, n in rows]


def check(topology: Graph, memory: Graph, req: ChangeCheckRequest) -> Analysis[ChangeCheck]:
    if not req.files and not req.services:
        raise BadRequest("give at least one file or service")
    if req.services:
        require_services(topology, req.services, "services")
    names = sorted(set(req.services) | services_for_files(topology, req.files))

    impacted: list[ImpactItem] = []
    risk = 0
    basis: Basis = "n/a"
    if names:
        result = impact.what_if(topology, WhatIfRequest(services=names))
        impacted, risk, basis = result.data.items, result.data.risk_score, result.basis
    nodes = service_nodes(topology, names)
    victims = [i.service.name for i in impacted]
    data = ChangeCheck(
        services=[nodes[n] for n in names if n in nodes],
        impacted=impacted,
        risk_score=risk,
        coupled_files=_coupled_files(topology, req.files, names),
        reviewers=responders.recommend(topology, memory, names),
        similar_incidents=incidents.find_similar(memory, [*names, *victims]),
    )
    return Analysis(data, basis)
