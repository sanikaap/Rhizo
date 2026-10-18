from datetime import UTC, datetime

from fastapi.testclient import TestClient

from rhizo.graph.client import GraphClient
from rhizo.models import BlastRadiusRequest, UpstreamSuspectsRequest, WhatIfRequest
from rhizo.services import impact


def _victims(gc: GraphClient, name: str, **kw: object) -> dict[str, list[str]]:
    result = impact.blast_radius(gc.topology(), BlastRadiusRequest(service=name, **kw))
    return {i.service.name: i.path for i in result.data.items}


def test_blast_radius_follows_paths_into_the_failing_service(tiny_graph: GraphClient) -> None:
    assert _victims(tiny_graph, "C") == {"B": ["svc:B", "svc:C"], "A": ["svc:A", "svc:B", "svc:C"]}
    assert _victims(tiny_graph, "B") == {"A": ["svc:A", "svc:B"]}


def test_nothing_breaks_when_the_top_dependent_fails(tiny_graph: GraphClient) -> None:
    assert _victims(tiny_graph, "A") == {}


def test_upstream_suspects_follow_paths_out_of_the_failing_service(tiny_graph: GraphClient) -> None:
    result = impact.upstream_suspects(tiny_graph.topology(), UpstreamSuspectsRequest(service="A"))
    assert {s.service.name: s.hops for s in result.data.suspects} == {"B": 1, "C": 2}
    suspects_of_c = impact.upstream_suspects(tiny_graph.topology(), UpstreamSuspectsRequest(service="C"))
    assert suspects_of_c.data.suspects == []


def test_resource_failure_enters_through_uses_then_depends_on(tiny_graph: GraphClient) -> None:
    assert _victims(tiny_graph, "R") == {
        "C": ["svc:C", "res:R"],
        "D": ["svc:D", "res:R"],
        "B": ["svc:B", "svc:C", "res:R"],
        "A": ["svc:A", "svc:B", "svc:C", "res:R"],
    }
    assert set(_victims(tiny_graph, "R", max_hops=1)) == {"C", "D"}


def test_item_basis_is_the_worst_provenance_on_the_path(tiny_graph: GraphClient) -> None:
    result = impact.blast_radius(tiny_graph.topology(), BlastRadiusRequest(service="B"))
    assert [i.basis for i in result.data.items] == ["declared"]
    result = impact.blast_radius(tiny_graph.topology(), BlastRadiusRequest(service="C"))
    assert {i.service.name: i.basis for i in result.data.items} == {"B": "inferred", "A": "inferred"}
    assert result.basis == "inferred"


def test_min_confidence_drops_weak_paths(tiny_graph: GraphClient) -> None:
    assert _victims(tiny_graph, "C", min_confidence=0.85) == {}


def test_service_without_depends_on_uses_connectivity_fallback(tiny_graph: GraphClient) -> None:
    result = impact.blast_radius(tiny_graph.topology(), BlastRadiusRequest(service="D"))
    assert [(i.service.name, i.basis) for i in result.data.items] == [("C", "connectivity_fallback")]
    assert result.basis == "connectivity_fallback"


def test_expired_edge_is_excluded_now_but_visible_as_of_before_expiry(tiny_graph: GraphClient) -> None:
    tiny_graph.topology().query("MATCH (:Service {name: 'A'})-[r:DEPENDS_ON]->() SET r.valid_to = 1000")
    assert _victims(tiny_graph, "B") == {}
    assert _victims(tiny_graph, "B", as_of=datetime.fromtimestamp(500, tz=UTC)) == {"A": ["svc:A", "svc:B"]}


def test_what_if_unions_victims_and_excludes_failed_roots(tiny_graph: GraphClient) -> None:
    result = impact.what_if(tiny_graph.topology(), WhatIfRequest(services=["B", "R"]))
    assert result.data.failed == ["B", "R"]
    assert {i.service.name: i.hops for i in result.data.items} == {"A": 1, "C": 1, "D": 1}


def test_blast_radius_api_contract(api: TestClient, tiny_graph: GraphClient) -> None:
    res = api.post("/api/impact/blast-radius", json={"service": "C"})
    assert res.status_code == 200
    body = res.json()
    first = body["data"]["items"][0]
    assert first["service"]["id"] == "svc:B"
    assert set(first["service"]["properties"]) >= {"tier", "team", "language"}
    assert "risk_score" not in first["service"]
    assert body["meta"]["basis"] == "inferred"
    assert body["meta"]["cypher"]


def test_unknown_and_invalid_names(api: TestClient, tiny_graph: GraphClient) -> None:
    unknown = api.post("/api/impact/blast-radius", json={"service": "nope"})
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (404, "NOT_FOUND")
    bad = api.post("/api/impact/blast-radius", json={"service": "x' OR 1=1"})
    assert (bad.status_code, bad.json()["error"]["code"]) == (400, "BAD_REQUEST")
    too_deep = api.post("/api/impact/blast-radius", json={"service": "C", "max_hops": 7})
    assert too_deep.status_code == 400


def test_impact_endpoints_return_503_when_falkordb_is_unreachable(api_db_down: TestClient) -> None:
    for path, body in (
        ("/api/impact/blast-radius", {"service": "C"}),
        ("/api/impact/upstream-suspects", {"service": "A"}),
        ("/api/impact/what-if", {"services": ["C"]}),
    ):
        res = api_db_down.post(path, json=body)
        assert (res.status_code, res.json()["error"]["code"]) == (503, "UPSTREAM"), path
