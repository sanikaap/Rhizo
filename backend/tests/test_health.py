from fastapi.testclient import TestClient

from rhizo.graph.client import GraphClient


def test_health_reports_falkordb_up(api: TestClient) -> None:
    res = api.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["data"] == {
        "status": "ok",
        "falkordb": "up",
        "graph_counts": {"services": 0, "edges": 0, "incidents": 0},
    }
    assert body["meta"]["basis"] == "n/a"
    assert len(body["meta"]["cypher"]) == 3


def test_health_db_unreachable_returns_503_upstream(api_db_down: TestClient) -> None:
    res = api_db_down.get("/api/health")
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "UPSTREAM"


def test_health_counts_only_live_dependency_edges(api: TestClient, tiny_graph: GraphClient) -> None:
    tiny_graph.topology().query(
        "MATCH (s:Service {name: 'A'}) "
        "CREATE (:Commit {sha: 'x'})-[:TOUCHED]->(:File {path: 'a'})-[:PART_OF]->(s)"
    )
    tiny_graph.topology().query("MATCH (:Service {name: 'A'})-[r:DEPENDS_ON]->() SET r.valid_to = 1")
    assert api.get("/api/health").json()["data"]["graph_counts"]["edges"] == 3
