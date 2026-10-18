import pytest
from fastapi.testclient import TestClient

from rhizo.graph.client import GraphClient


@pytest.fixture
def repo_graph(tiny_graph: GraphClient) -> GraphClient:
    g = tiny_graph.topology()
    g.query("MATCH (s:Service) SET s.path_prefix = 'src/' + s.name + '/'")
    g.query(
        """
        UNWIND [['c1', false], ['c2', false], ['bot1', true]] AS c
        CREATE (:Commit {sha: c[0], bot: c[1], files_count: 2})
        """
    )
    g.query(
        """
        UNWIND [['c1', 'src/C/x.go'], ['c1', 'src/D/y.go'], ['c2', 'src/C/x.go'], ['c2', 'src/D/y.go'],
                ['bot1', 'src/C/x.go'], ['bot1', 'src/A/z.go']] AS t
        MATCH (c:Commit {sha: t[0]})
        MERGE (f:File {path: t[1]})
        CREATE (c)-[:TOUCHED]->(f)
        """
    )
    g.query("MATCH (f:File), (s:Service) WHERE f.path STARTS WITH s.path_prefix MERGE (f)-[:PART_OF]->(s)")
    return tiny_graph


def _check(api: TestClient, **body: object) -> dict[str, object]:
    res = api.post("/api/impact/change-check", json=body)
    assert res.status_code == 200, res.text
    data: dict[str, object] = res.json()
    return data


def test_files_map_to_services_and_impact(api: TestClient, repo_graph: GraphClient) -> None:
    body = _check(api, files=["src/C/x.go", "src/C/brand_new.go"])
    data = body["data"]
    assert isinstance(data, dict)
    assert [s["id"] for s in data["services"]] == ["svc:C"]
    assert {i["service"]["name"] for i in data["impacted"]} == {"B", "A"}
    assert data["risk_score"] > 0
    assert data["coupled_files"] == [{"path": "src/D/y.go", "count": 2}]
    assert set(data) == {
        "services",
        "impacted",
        "risk_score",
        "coupled_files",
        "reviewers",
        "similar_incidents",
    }
    meta = body["meta"]
    assert isinstance(meta, dict)
    assert any("TOUCHED" in c for c in meta["cypher"]) and meta["basis"] == "inferred"


def test_services_only_couples_against_the_services_files(api: TestClient, repo_graph: GraphClient) -> None:
    data = _check(api, services=["D"])["data"]
    assert isinstance(data, dict)
    assert data["coupled_files"] == [{"path": "src/C/x.go", "count": 2}]


def test_unowned_files_give_an_empty_but_valid_answer(api: TestClient, repo_graph: GraphClient) -> None:
    data = _check(api, files=["README.md"])["data"]
    assert data == {
        "services": [],
        "impacted": [],
        "risk_score": 0,
        "coupled_files": [],
        "reviewers": [],
        "similar_incidents": [],
    }


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"files": [], "services": []},
        {"services": ["nope"]},
        {"services": ["R"]},
        {"files": ["../etc/passwd"]},
    ],
)
def test_bad_requests(api: TestClient, repo_graph: GraphClient, body: dict[str, object]) -> None:
    res = api.post("/api/impact/change-check", json=body)
    assert (res.status_code, res.json()["error"]["code"]) == (400, "BAD_REQUEST")


def test_change_check_503_when_falkordb_is_unreachable(api_db_down: TestClient) -> None:
    res = api_db_down.post("/api/impact/change-check", json={"services": ["C"]})
    assert (res.status_code, res.json()["error"]["code"]) == (503, "UPSTREAM")
