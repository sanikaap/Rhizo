from falkordb import Graph

from rhizo.graph import algos
from rhizo.graph import queries as Q
from rhizo.graph.client import run

TIER1_SHARE = 0.75


def assign(topology: Graph) -> dict[str, int]:
    scores = algos.pagerank(topology)
    dependents = algos.degrees(topology).dependents
    central = {s: scores.values.get(s, 0.0) for s, n in dependents.items() if n > 0}
    top = max(central.values(), default=0.0)

    def tier(service: str) -> int:
        if service not in central:
            return 3
        return 1 if top > 0 and central[service] / top >= TIER1_SHARE else 2

    tiers = {s: tier(s) for s in dependents}
    basis = f"pagerank ({scores.algorithm})"
    run(
        topology,
        "set_tiers",
        Q.SET_TIERS,
        {"rows": [{"name": s, "tier": t, "basis": basis} for s, t in tiers.items()]},
    )
    return tiers
