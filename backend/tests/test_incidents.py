import pytest
from fastapi.testclient import TestClient

from rhizo.graph.client import GraphClient, run


@pytest.fixture
def team(tiny_graph: GraphClient) -> GraphClient:
    tiny_graph.topology().query("CREATE (:Engineer {handle: 'alice', name: 'Alice'})")
    return tiny_graph


def _open(api: TestClient, *affected: str) -> str:
    res = api.post(
        "/api/incidents", json={"title": "t", "symptom": "s", "severity": "sev2", "affected": list(affected)}
    )
    assert res.status_code == 200, res.text
    incident_id: str = res.json()["data"]["id"]
    return incident_id


def _resolve(api: TestClient, incident_id: str, **body: object) -> dict[str, object]:
    res = api.post(f"/api/incidents/{incident_id}/resolve", json={"root_cause": "C", "fix": "f", **body})
    assert res.status_code == 200, res.text
    data: dict[str, object] = res.json()["data"]
    return data


def _edge(gc: GraphClient, a: str, b: str) -> list[object]:
    rows = run(
        gc.topology(),
        "t_edge",
        "MATCH (:Service {name: $a})-[r:DEPENDS_ON]->(:Service {name: $b}) "
        "RETURN r.confidence, r.source, r.valid_to, r.evidence, r.incident_id",
        {"a": a, "b": b},
    )
    return rows[0] if rows else []


def test_confirmed_edge_is_created_at_060_then_strengthened_to_075(
    api: TestClient, team: GraphClient
) -> None:
    first = _open(api, "D")
    result = _resolve(api, first, confirmed_edges=[{"from": "D", "to": "C"}])
    assert result["graph_updates"] == {"created": 1, "strengthened": 0, "weakened": 0}
    assert _edge(team, "D", "C") == [0.6, "inferred", None, f"Revealed by {first}", first]

    second = _open(api, "D")
    result = _resolve(api, second, confirmed_edges=[{"from": "D", "to": "C"}])
    assert result["graph_updates"] == {"created": 0, "strengthened": 1, "weakened": 0}
    conf = _edge(team, "D", "C")[0]
    assert conf == pytest.approx(0.75)


def test_strengthening_caps_at_one(api: TestClient, team: GraphClient) -> None:
    for _ in range(2):
        _resolve(api, _open(api, "A"), confirmed_edges=[{"from": "A", "to": "B"}])
    assert _edge(team, "A", "B")[0] == 1.0


def test_refutation_lowers_confidence_with_a_floor(api: TestClient, team: GraphClient) -> None:
    result = _resolve(api, _open(api, "A"), refuted_edges=[{"from": "A", "to": "B"}])
    assert result["graph_updates"] == {"created": 0, "strengthened": 0, "weakened": 1}
    assert _edge(team, "A", "B")[0] == pytest.approx(0.70)
    for _ in range(5):
        _resolve(api, _open(api, "A"), refuted_edges=[{"from": "A", "to": "B"}])
    assert _edge(team, "A", "B")[0] == pytest.approx(0.05)
    none = _resolve(api, _open(api, "A"), refuted_edges=[{"from": "A", "to": "D"}])
    assert none["graph_updates"] == {"created": 0, "strengthened": 0, "weakened": 0}
    assert _edge(team, "A", "D") == []


def test_confirming_an_expired_edge_revives_it(api: TestClient, team: GraphClient) -> None:
    team.topology().query("MATCH (:Service {name: 'B'})-[r:DEPENDS_ON]->() SET r.valid_to = 1000")
    blast = api.post("/api/impact/blast-radius", json={"service": "C"}).json()["data"]
    assert not {"A", "B"} & {i["service"]["name"] for i in blast["items"]}

    result = _resolve(api, _open(api, "B"), confirmed_edges=[{"from": "B", "to": "C"}])
    assert result["graph_updates"] == {"created": 0, "strengthened": 1, "weakened": 0}
    conf, _, valid_to, *_ = _edge(team, "B", "C")
    assert (conf, valid_to) == (pytest.approx(0.95), None)
    blast = api.post("/api/impact/blast-radius", json={"service": "C"}).json()["data"]
    assert {i["service"]["name"] for i in blast["items"]} >= {"A", "B"}


def test_write_back_is_visible_in_the_cached_graph_view(api: TestClient, team: GraphClient) -> None:
    before = {e["id"] for e in api.get("/api/graph").json()["data"]["edges"]}
    _resolve(api, _open(api, "D"), confirmed_edges=[{"from": "D", "to": "C"}])
    after = {e["id"] for e in api.get("/api/graph").json()["data"]["edges"]}
    assert after - before == {"DEPENDS_ON:svc:D->svc:C"}


@pytest.mark.parametrize(("root_cause", "label"), [("R", "Resource"), ("C", "Service")])
def test_root_cause_targets_the_topology_label(
    api: TestClient, team: GraphClient, root_cause: str, label: str
) -> None:
    incident_id = _open(api, "A")
    _resolve(api, incident_id, root_cause="A")
    data = _resolve(api, incident_id, root_cause=root_cause, resolved_by="alice")
    rows = run(
        team.memory(),
        "t_rc",
        "MATCH (:Incident {id: $id})-[:ROOT_CAUSE]->(n) RETURN labels(n)[0], n.name",
        {"id": incident_id},
    )
    assert rows == [[label, root_cause]]
    incident = data["incident"]
    assert isinstance(incident, dict)
    assert (incident["status"], incident["root_cause"], incident["resolved_by"]) == (
        "resolved",
        root_cause,
        "alice",
    )


@pytest.mark.parametrize(
    "body",
    [
        {"root_cause": "nope"},
        {"root_cause": "C", "resolved_by": "nobody"},
        {"root_cause": "C", "confirmed_edges": [{"from": "A", "to": "R"}]},
        {"root_cause": "C", "confirmed_edges": [{"from": "A", "to": "A"}]},
        {"root_cause": "C", "confirmed_edges": [{"from": "A", "to": "a b"}]},
    ],
)
def test_bad_resolution_is_rejected_before_any_write(
    api: TestClient, team: GraphClient, body: dict[str, object]
) -> None:
    incident_id = _open(api, "A")
    res = api.post(f"/api/incidents/{incident_id}/resolve", json={"fix": "f", **body})
    assert res.status_code == 400
    assert api.get(f"/api/incidents/{incident_id}").json()["data"]["incident"]["status"] == "open"


def test_create_list_and_detail(api: TestClient, team: GraphClient) -> None:
    first, second = _open(api, "C"), _open(api, "C", "D")
    assert (first, second) == ("INC-101", "INC-102")
    assert [i["id"] for i in api.get("/api/incidents").json()["data"]] == ["INC-102", "INC-101"]

    detail = api.get(f"/api/incidents/{first}").json()["data"]
    assert detail["suggested_edges"] == [{"from": "C", "to": "D", "type": "DEPENDS_ON", "reason": "Shared R"}]
    assert [(s["incident"]["id"], s["similarity"]) for s in detail["similar"]] == [(second, 0.5)]
    assert api.get("/api/incidents/INC-999").status_code == 404
    assert (
        api.post(
            "/api/incidents", json={"title": "t", "symptom": "s", "severity": "sev2", "affected": ["R"]}
        ).status_code
        == 400
    )


def test_responders_combine_commits_and_resolutions(api: TestClient, team: GraphClient) -> None:
    team.topology().query(
        "MATCH (e:Engineer {handle: 'alice'}), (s:Service {name: 'C'}) "
        "CREATE (e)-[:COMMITTED_TO {count: 3, last_at: timestamp() / 1000}]->(s), "
        "(:Engineer {handle: 'bob', name: 'Bob'})"
        "-[:COMMITTED_TO {count: 1, last_at: timestamp() / 1000}]->(s)"
    )
    _resolve(api, _open(api, "C"), resolved_by="bob")
    res = api.get("/api/responders", params=[("service", "C")]).json()["data"]
    scores = {r["engineer"]["properties"]["handle"]: r["score"] for r in res}
    assert scores == {"bob": pytest.approx(0.6, abs=0.01), "alice": pytest.approx(0.6, abs=0.01)}
    assert {r["reason"] for r in res} >= {"Recent commits to C; resolved 1 related incident"}
