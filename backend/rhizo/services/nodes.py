from falkordb import Graph

from rhizo.core.errors import BadRequest, NotFound
from rhizo.graph import queries as Q
from rhizo.graph.client import Row, run
from rhizo.models import GraphNode


def nodes_from_service_rows(rows: list[Row]) -> dict[str, GraphNode]:
    nodes: dict[str, GraphNode] = {}
    for name, tier, language, repo, prefix, team in rows:
        if name not in nodes:
            nodes[name] = GraphNode(
                id=f"svc:{name}",
                label="Service",
                name=name,
                properties={
                    "tier": tier,
                    "language": language,
                    "team": team,
                    "repo": repo,
                    "path_prefix": prefix,
                },
            )
    return nodes


def service_nodes(topology: Graph, names: list[str]) -> dict[str, GraphNode]:
    if not names:
        return {}
    rows = run(topology, "service_nodes", Q.SERVICE_NODES, {"names": sorted(set(names))})
    return nodes_from_service_rows(rows)


def engineer_node(
    handle: str, name: str | None, pseudonymous: bool | None, commits: int | None = None
) -> GraphNode:
    props: dict[str, str | int | bool | None] = {
        "handle": handle,
        "team": None,
        "pseudonymous": bool(pseudonymous),
    }
    if commits is not None:
        props["commits"] = commits
    return GraphNode(id=f"eng:{handle}", label="Engineer", name=name or handle, properties=props)


def resource_node(name: str, kind: str | None) -> GraphNode:
    return GraphNode(id=f"res:{name}", label="Resource", name=name, properties={"kind": kind})


def split_roots(topology: Graph, names: list[str]) -> tuple[list[str], list[str]]:
    rows = run(topology, "root_labels", Q.ROOT_LABELS, {"names": names})
    services = [name for name, is_service, _ in rows if is_service]
    resources = [name for name, is_service, is_resource in rows if is_resource and not is_service]
    unknown = sorted(set(names) - set(services) - set(resources))
    if unknown:
        raise NotFound(f"no service or resource named {', '.join(unknown)}")
    return services, resources


def require_services(topology: Graph, names: list[str], what: str) -> None:
    try:
        _, resources = split_roots(topology, sorted(set(names)))
    except NotFound as e:
        raise BadRequest(f"{what}: {e.message}") from e
    if resources:
        raise BadRequest(f"{what} must be services, not resources: {', '.join(resources)}")
