from fastapi.testclient import TestClient

from rhizo.graph.client import GraphClient


def _expire_a_to_b(gc: GraphClient) -> None:
    gc.topology().query("MATCH (:Service {name: 'A'})-[r:DEPENDS_ON]->() SET r.valid_to = 1000")


def _edge_ids(api: TestClient, **query: str | float) -> set[str]:
    res = api.get("/api/graph", params=query)
    assert res.status_code == 200, res.text
    return {e["id"] for e in res.json()["data"]["edges"]}


def test_edge_ids_follow_the_contract(api: TestClient, tiny_graph: GraphClient) -> None:
    assert _edge_ids(api) == {
        "DEPENDS_ON:svc:A->svc:B",
        "DEPENDS_ON:svc:B->svc:C",
        "USES:svc:C->res:R",
        "USES:svc:D->res:R",
    }


def test_expired_edge_is_hidden_now_and_visible_as_of_before_expiry(
    api: TestClient, tiny_graph: GraphClient
) -> None:
    _expire_a_to_b(tiny_graph)
    assert "DEPENDS_ON:svc:A->svc:B" not in _edge_ids(api)
    assert "DEPENDS_ON:svc:A->svc:B" in _edge_ids(api, as_of="1970-01-01T00:08:20Z")
    assert "DEPENDS_ON:svc:A->svc:B" not in _edge_ids(api, as_of="1970-01-01T00:16:40Z")


def test_graph_filters(api: TestClient, tiny_graph: GraphClient) -> None:
    assert _edge_ids(api, provenance="inferred") == {"DEPENDS_ON:svc:B->svc:C", "USES:svc:D->res:R"}
    assert _edge_ids(api, min_confidence=0.9) == {"DEPENDS_ON:svc:A->svc:B", "USES:svc:C->res:R"}
    res = api.get("/api/graph", params={"center": "A", "depth": 1})
    assert {n["id"] for n in res.json()["data"]["nodes"]} == {"svc:A", "svc:B"}


def test_graph_rejects_bad_filters(api: TestClient, tiny_graph: GraphClient) -> None:
    assert api.get("/api/graph", params={"provenance": "guessed"}).status_code == 400
    assert api.get("/api/graph", params={"center": "nope"}).status_code == 404
    assert api.get("/api/graph", params={"center": "a b"}).status_code == 400


def test_services_carry_tier_team_language(api: TestClient, graph_client: GraphClient) -> None:
    graph_client.topology().query("CREATE (:Service {name: 'A', tier: 1, language: 'go'})")
    [node] = api.get("/api/services").json()["data"]
    assert node["id"] == "svc:A"
    assert {k: node["properties"][k] for k in ("tier", "team", "language")} == {
        "tier": 1,
        "team": None,
        "language": "go",
    }


def test_service_detail(api: TestClient, tiny_graph: GraphClient) -> None:
    res = api.get("/api/services/B")
    assert res.status_code == 200
    detail = res.json()["data"]
    assert detail["node"]["id"] == "svc:B"
    assert [(u["service"]["name"], u["path"]) for u in detail["upstream"]] == [("C", ["svc:B", "svc:C"])]
    assert detail["blast_radius_count"] == 1
    assert detail["responders"] == []
    assert api.get("/api/services/C").json()["data"]["resources"][0]["id"] == "res:R"


def test_service_detail_is_404_for_resources_and_unknown_names(
    api: TestClient, tiny_graph: GraphClient
) -> None:
    assert api.get("/api/services/R").status_code == 404
    assert api.get("/api/services/nope").status_code == 404
