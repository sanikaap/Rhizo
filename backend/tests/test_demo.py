from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from rhizo.config import settings
from rhizo.graph.client import GraphClient, repo_prefix, run
from rhizo.main import app
from rhizo.repos import demo, github, gitops, jobs, registry
from rhizo.repos.registry import Repo
from tests.conftest import make_token
from tests.test_sync import COMPOSE, PEOPLE, _commit, _git

ALICE = "user-alice"
BOB = "user-bob"


def _as(user: str) -> TestClient:
    return TestClient(app, headers={"Authorization": f"Bearer {make_token(user)}"})


def _repos(user: str) -> list[dict[str, Any]]:
    res = _as(user).get("/api/repos")
    assert res.status_code == 200
    return list(res.json()["data"])


@pytest.fixture
def demo_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "demo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _commit(repo, PEOPLE[0], "initial", {"docker-compose.yml": COMPOSE, "web/package.json": '{"name": "web"}',
            "web/index.js": "x", "api/requirements.txt": "", "api/app.py": "x = 1\n"})  # fmt: skip
    _commit(repo, PEOPLE[1], "fix: handle a null price", {"api/app.py": "x = 2\n"})
    monkeypatch.setattr(settings, "demo_repo_path", repo)
    return repo


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: object) -> None:
        raise AssertionError("the bundled demo must not reach GitHub")

    @contextmanager
    def no_clone(url: str) -> Iterator[Path]:
        refuse(url)
        yield Path()

    monkeypatch.setattr(github, "repo_info", refuse)
    monkeypatch.setattr(gitops, "clone", no_clone)
    monkeypatch.setattr(github, "closed_issues", lambda ref, label: [])


@pytest.fixture
def drop_graphs() -> Iterator[list[Repo]]:
    made: list[Repo] = []
    yield made
    for repo in made:
        GraphClient(repo_prefix(repo.user_id, repo.id)).drop()


def test_first_visit_provisions_one_demo_in_the_background(_isolated: list[str]) -> None:
    first = _repos(ALICE)
    assert [(r["full_name"], r["is_demo"], r["status"]) for r in first] == [
        (f"{demo.OWNER}/{demo.NAME}", True, "queued")
    ]
    assert _isolated == [first[0]["id"]]
    assert _repos(ALICE) == first
    assert _isolated == [first[0]["id"]]


def test_removed_demo_is_never_provisioned_again(_isolated: list[str]) -> None:
    demo_id = _repos(ALICE)[0]["id"]
    res = _as(ALICE).delete(f"/api/repos/{demo_id}")
    assert res.status_code == 200
    assert registry.demo_dismissed(ALICE)
    assert _repos(ALICE) == []
    assert _repos(ALICE) == []
    assert registry.get(ALICE, demo_id) is None


def test_load_demo_restores_it(_isolated: list[str]) -> None:
    demo_id = _repos(ALICE)[0]["id"]
    _as(ALICE).delete(f"/api/repos/{demo_id}")
    res = _as(ALICE).post("/api/repos/demo")
    assert res.status_code == 201
    restored = res.json()["data"]
    assert (restored["is_demo"], restored["status"]) == (True, "queued")
    assert restored["id"] != demo_id
    assert not registry.demo_dismissed(ALICE)
    assert [r["id"] for r in _repos(ALICE)] == [restored["id"]]
    assert _isolated[-1] == restored["id"]


def test_load_demo_when_present_returns_the_existing_one() -> None:
    demo_id = _repos(ALICE)[0]["id"]
    res = _as(ALICE).post("/api/repos/demo")
    assert (res.status_code, res.json()["data"]["id"]) == (201, demo_id)
    assert len(_repos(ALICE)) == 1


def test_an_existing_account_without_a_demo_is_not_provisioned() -> None:
    registry.ensure_account(ALICE)
    assert _repos(ALICE) == []


def test_removing_one_users_demo_leaves_others_alone(
    demo_source: Path, offline: None, drop_graphs: list[Repo]
) -> None:
    alice_id, bob_id = _repos(ALICE)[0]["id"], _repos(BOB)[0]["id"]
    assert alice_id != bob_id
    for user, repo_id in ((ALICE, alice_id), (BOB, bob_id)):
        jobs.run_sync(repo_id)
        repo = registry.get(user, repo_id)
        assert repo is not None and repo.status == "ready", repo
        drop_graphs.append(repo)

    assert _as(BOB).delete(f"/api/repos/{alice_id}").status_code == 404
    assert _as(ALICE).delete(f"/api/repos/{alice_id}").status_code == 200

    assert registry.demo_dismissed(ALICE) and not registry.demo_dismissed(BOB)
    assert [r["id"] for r in _repos(BOB)] == [bob_id]
    bob_graph = GraphClient(repo_prefix(BOB, bob_id)).topology()
    assert run(bob_graph, "t", "MATCH (s:Service) RETURN count(s)") == [[2]]
    alice_graph = GraphClient(repo_prefix(ALICE, alice_id)).topology()
    assert run(alice_graph, "t", "MATCH (n) RETURN count(n)") == [[0]]


def test_demo_sync_reads_the_bundled_checkout_and_stores_an_evaluation(
    demo_source: Path, offline: None, drop_graphs: list[Repo]
) -> None:
    demo_id = _repos(ALICE)[0]["id"]
    jobs.run_sync(demo_id)
    repo = registry.get(ALICE, demo_id)
    assert repo is not None
    drop_graphs.append(repo)
    assert (repo.status, repo.error) == ("ready", None)
    assert repo.message and repo.message.startswith("2 services")

    res = _as(ALICE).get("/api/benchmark/results", headers={"X-Repo-Id": demo_id})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["status"] == "insufficient_history"
    assert data["commits_total"] == 2
    assert data["systems"] == []


def test_benchmark_without_a_sync_is_not_found(test_repo: Repo) -> None:
    res = _as(test_repo.user_id).get("/api/benchmark/results", headers={"X-Repo-Id": test_repo.id})
    assert (res.status_code, res.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_another_users_benchmark_is_not_found(test_repo: Repo) -> None:
    registry.save_evaluation(test_repo.id, '{"status": "ok"}')
    res = _as(BOB).get("/api/benchmark/results", headers={"X-Repo-Id": test_repo.id})
    assert (res.status_code, res.json()["error"]["code"]) == (404, "NOT_FOUND")
