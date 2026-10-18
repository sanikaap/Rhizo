from falkordb import Graph

from rhizo.graph import queries as Q
from rhizo.graph.client import run
from rhizo.graph.scoring import SHARED_RESOURCE_CONFIDENCE
from rhizo.models import HiddenDependency
from rhizo.services.nodes import resource_node, service_nodes

CO_CHANGE_MIN_CONFIDENCE = 0.5


def find_hidden(topology: Graph, service: str | None = None) -> list[HiddenDependency]:
    params: dict[str, object] = {"name": service, "min_conf": CO_CHANGE_MIN_CONFIDENCE}
    shared = run(topology, "hidden_shared_resource", Q.HIDDEN_SHARED_RESOURCE, params)
    cochange = run(topology, "hidden_co_change", Q.HIDDEN_CO_CHANGE, params)
    nodes = service_nodes(topology, [name for row in (*shared, *cochange) for name in row[:2]])

    found = [
        HiddenDependency(
            id=f"hidden:svc:{a}~svc:{b}~res:{res}",
            kind="shared_resource",
            a=nodes[a],
            b=nodes[b],
            via=resource_node(res, kind),
            confidence=SHARED_RESOURCE_CONFIDENCE,
            evidence=f'Both use {kind or "resource"} "{res}" but no DEPENDS_ON path connects them.',
        )
        for a, b, res, kind in shared
    ] + [
        HiddenDependency(
            id=f"hidden:svc:{a}~svc:{b}",
            kind="co_change",
            a=nodes[a],
            b=nodes[b],
            confidence=conf,
            support=support,
            jaccard=jaccard,
            evidence=(
                f"Changed together in {support} commits (Jaccard {jaccard:.2f}) with no declared dependency."
            ),
        )
        for a, b, support, jaccard, conf in cochange
    ]
    return sorted(found, key=lambda h: (-h.confidence, h.id))
