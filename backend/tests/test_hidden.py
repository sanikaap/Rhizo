from fastapi.testclient import TestClient

from rhizo.graph.client import GraphClient
from rhizo.services.hidden import find_hidden


def _pairs(gc: GraphClient, service: str | None = None) -> set[tuple[str, str, str]]:
    return {(h.kind, h.a.name, h.b.name) for h in find_hidden(gc.topology(), service)}


def _cypher(gc: GraphClient, query: str) -> None:
    gc.topology().query(query)


def test_shared_resource_without_a_path_is_hidden(tiny_graph: GraphClient) -> None:
    [dep] = find_hidden(tiny_graph.topology())
    assert (dep.kind, dep.a.name, dep.b.name) == ("shared_resource", "C", "D")
    assert dep.via is not None and dep.via.id == "res:R"
    assert dep.confidence == 0.70


def test_declared_path_in_either_direction_removes_it(tiny_graph: GraphClient) -> None:
    _cypher(
        tiny_graph, "MATCH (d:Service {name: 'D'}), (c:Service {name: 'C'}) CREATE (d)-[:DEPENDS_ON]->(c)"
    )
    assert _pairs(tiny_graph) == set()


def test_multi_hop_reverse_path_removes_it(tiny_graph: GraphClient) -> None:
    _cypher(
        tiny_graph,
        "MATCH (c:Service {name: 'C'}), (d:Service {name: 'D'}) "
        "CREATE (c)-[:DEPENDS_ON]->(:Service {name: 'X'})-[:DEPENDS_ON]->(d)",
    )
    assert _pairs(tiny_graph) == set()


def test_common_dependent_does_not_hide_the_pair(tiny_graph: GraphClient) -> None:
    _cypher(
        tiny_graph,
        "MATCH (c:Service {name: 'C'}), (d:Service {name: 'D'}) "
        "CREATE (c)<-[:DEPENDS_ON]-(:Service {name: 'Y'})-[:DEPENDS_ON]->(d)",
    )
    assert _pairs(tiny_graph) == {("shared_resource", "C", "D")}


def test_expired_path_does_not_hide_the_pair(tiny_graph: GraphClient) -> None:
    _cypher(
        tiny_graph,
        "MATCH (d:Service {name: 'D'}), (c:Service {name: 'C'}) CREATE (d)-[:DEPENDS_ON {valid_to: 1}]->(c)",
    )
    assert _pairs(tiny_graph) == {("shared_resource", "C", "D")}


def test_co_change_pair_is_hidden_unless_declared(tiny_graph: GraphClient) -> None:
    _cypher(
        tiny_graph,
        "MATCH (a:Service {name: 'A'}), (d:Service {name: 'D'}) "
        "CREATE (a)-[:CO_CHANGES_WITH {source: 'inferred', confidence: 0.6, support: 4, jaccard: 0.4}]->(d)",
    )
    deps = {h.kind: h for h in find_hidden(tiny_graph.topology(), "A")}
    assert set(deps) == {"co_change"}
    assert (deps["co_change"].support, deps["co_change"].jaccard) == (4, 0.4)

    _cypher(
        tiny_graph, "MATCH (a:Service {name: 'A'}), (d:Service {name: 'D'}) CREATE (a)-[:DEPENDS_ON]->(d)"
    )
    assert ("co_change", "A", "D") not in _pairs(tiny_graph)


def test_service_filter(tiny_graph: GraphClient) -> None:
    assert _pairs(tiny_graph, "C") == {("shared_resource", "C", "D")}
    assert _pairs(tiny_graph, "A") == set()


def test_hidden_dependencies_api(api: TestClient, tiny_graph: GraphClient) -> None:
    res = api.get("/api/hidden-dependencies")
    body = res.json()
    assert res.status_code == 200
    assert body["meta"]["basis"] == "inferred"
    [item] = body["data"]
    assert item["id"] == "hidden:svc:C~svc:D~res:R"
    assert "support" not in item
    assert api.get("/api/hidden-dependencies", params={"service": "x y"}).status_code == 400
