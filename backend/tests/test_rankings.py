import pytest
from fastapi.testclient import TestClient

from rhizo.graph import queries
from rhizo.graph import version as graph_version
from rhizo.graph.client import GraphClient
from rhizo.services.rankings import rank


def _order(gc: GraphClient, metric: str) -> list[str]:
    return [i.service.name for i in rank(gc.topology(), metric, 10).items]  # type: ignore[arg-type]


def test_pagerank_uses_falkordb_and_ranks_the_most_depended_upon_first(tiny_graph: GraphClient) -> None:
    result = rank(tiny_graph.topology(), "pagerank", 10)
    assert result.algorithm == "falkordb"
    assert result.items[0].service.name == "C"
    assert result.items[0].score == 1.0


def test_centrality_is_an_honestly_labelled_degree_fallback(tiny_graph: GraphClient) -> None:
    result = rank(tiny_graph.topology(), "centrality", 10)
    assert result.algorithm == "degree_fallback"
    assert [i.service.name for i in result.items[:2]] == ["B", "C"]


def test_missing_procedure_falls_back_to_degree_and_says_so(
    tiny_graph: GraphClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        queries, "PAGERANK", "CALL algo.noSuchRank('Service') YIELD node, score RETURN node, score"
    )
    result = rank(tiny_graph.topology(), "pagerank", 10)
    assert result.algorithm == "degree_fallback"
    assert {i.service.name: i.score for i in result.items} == {"B": 1.0, "C": 1.0, "A": 0.0, "D": 0.0}


def test_community_metric_sets_one_based_communities(tiny_graph: GraphClient) -> None:
    result = rank(tiny_graph.topology(), "community", 10)
    assert result.algorithm == "falkordb"
    communities = {i.service.name: i.community for i in result.items if i.community is not None}
    assert len(communities) == len(result.items) and min(communities.values()) == 1
    sizes = [list(communities.values()).count(c) for c in range(1, max(communities.values()) + 1)]
    assert all(sizes) and sizes == sorted(sizes, reverse=True)


def test_rankings_are_cached_until_the_graph_version_changes(tiny_graph: GraphClient) -> None:
    assert _order(tiny_graph, "pagerank")[0] == "C"
    g = tiny_graph.topology()
    g.query(
        "MATCH (s:Service) WHERE s.name IN ['A', 'B', 'C'] "
        "MATCH (d:Service {name: 'D'}) CREATE (s)-[:DEPENDS_ON {valid_from: 0}]->(d)"
    )
    assert _order(tiny_graph, "pagerank")[0] == "C"
    graph_version.bump(g, now=1)
    assert _order(tiny_graph, "pagerank")[0] == "D"


def test_rankings_api(api: TestClient, tiny_graph: GraphClient) -> None:
    res = api.get("/api/rankings", params={"metric": "community", "top_k": 2})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["metric"] == "community" and data["algorithm"] == "falkordb"
    assert len(data["items"]) == 2 and all("community" in i for i in data["items"])
    pagerank = api.get("/api/rankings").json()["data"]
    assert "community" not in pagerank["items"][0]
    assert api.get("/api/rankings", params={"metric": "vibes"}).status_code == 400
    assert api.get("/api/rankings", params={"top_k": 51}).status_code == 400


def test_graph_and_services_carry_risk_scores(api: TestClient, tiny_graph: GraphClient) -> None:
    nodes = {n["id"]: n for n in api.get("/api/graph").json()["data"]["nodes"]}
    assert nodes["svc:C"]["risk_score"] == 100
    assert "risk_score" not in nodes["res:R"]
    services = api.get("/api/services").json()["data"]
    assert all(isinstance(s["risk_score"], int) for s in services)
