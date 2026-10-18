import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from rhizo.config import settings
from rhizo.graph.client import GraphClient, run
from rhizo.ingest import git_history
from rhizo.repos import github, gitops, jobs, pipeline, registry
from rhizo.repos.github import GitHubError, RepoInfo, RepoRef
from rhizo.repos.registry import Repo

PEOPLE = [("Ada Realname", "ada@example.org"), ("Grace Realname", "grace@example.org")]
BOT = ("renovate[bot]", "bot@renovateapp.com")


def _git(repo: Path, *args: str, author: tuple[str, str] | None = None) -> None:
    ident = ["-c", f"user.name={author[0]}", "-c", f"user.email={author[1]}"] if author else []
    subprocess.run(["git", *ident, "-C", str(repo), *args], check=True, capture_output=True)


def _commit(repo: Path, author: tuple[str, str], message: str, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message, author=author)


COMPOSE = (
    "services:\n"
    "  web: {build: ./web, depends_on: [api]}\n"
    "  api: {build: ./api, depends_on: [db]}\n"
    "  db: {image: postgres:16}\n"
)


@pytest.fixture
def source(tmp_path: Path) -> Path:
    repo = tmp_path / "src-repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _commit(repo, PEOPLE[0], "initial", {"docker-compose.yml": COMPOSE, "web/package.json": '{"name": "web"}',
            "web/index.js": "x", "api/requirements.txt": "", "api/app.py": "x = 1\n"})  # fmt: skip
    _commit(repo, PEOPLE[1], "fix: handle a null price", {"api/app.py": "x = 2\n"})
    _commit(repo, PEOPLE[0], "Guard empty carts, closes #7", {"web/index.js": "y", "api/app.py": "x = 3\n"})
    _commit(repo, BOT, "chore(deps): bump everything", {"web/index.js": "z"})
    return repo


ISSUES = [
    {"number": 7, "title": "Checkout crashes on empty cart",
     "body": "<!-- template -->\nSteps: open cart\nmore",
     "labels": [{"name": "bug"}, {"name": "P1"}], "created_at": "2026-01-02T03:04:05Z",
     "closed_at": "2026-01-03T00:00:00Z", "html_url": "https://github.com/acme/shop/issues/7"},
    {"number": 8, "title": "Unlinked bug", "body": "", "labels": [{"name": "bug"}],
     "created_at": "2026-01-02T00:00:00Z", "closed_at": "2026-01-02T01:00:00Z", "html_url": "https://x/8"},
]  # fmt: skip


@pytest.fixture
def fake_github(monkeypatch: pytest.MonkeyPatch, source: Path) -> dict[str, Any]:
    state: dict[str, Any] = {"issues": ISSUES, "info_error": None}

    def info(ref: RepoRef) -> RepoInfo:
        if state["info_error"]:
            raise state["info_error"]
        return RepoInfo(ref.owner, ref.name, 1, "main")

    def issues(ref: RepoRef, label: str) -> list[dict[str, Any]]:
        if isinstance(state["issues"], Exception):
            raise state["issues"]
        return [i for i in state["issues"] if label in {lbl["name"] for lbl in i["labels"]}]

    @contextmanager
    def clone(url: str) -> Iterator[Path]:
        dest = source.parent / "checkout"
        shutil.copytree(source, dest)
        try:
            yield dest
        finally:
            shutil.rmtree(dest)

    monkeypatch.setattr(github, "repo_info", info)
    monkeypatch.setattr(github, "closed_issues", issues)
    monkeypatch.setattr(gitops, "clone", clone)
    return state


@pytest.fixture
def synced(graph_client: GraphClient, test_repo: Repo, fake_github: dict[str, Any]) -> Repo:
    jobs.run_sync(test_repo.id)
    repo = registry.get_any(test_repo.id)
    assert repo is not None
    return repo


def _rows(gc: GraphClient, cypher: str, memory: bool = False) -> list[list[Any]]:
    return run(gc.memory() if memory else gc.topology(), "t", cypher)


def _counts(gc: GraphClient) -> dict[str, int]:
    labels = _rows(gc, "MATCH (n) RETURN labels(n)[0], count(n)")
    rels = _rows(gc, "MATCH ()-[r]->() RETURN type(r), count(r)")
    memory = _rows(gc, "MATCH ()-[r]->() RETURN type(r), count(r)", memory=True)
    return {
        **{f"n:{k}": v for k, v in labels},
        **{f"r:{k}": v for k, v in rels},
        **{f"m:{k}": v for k, v in memory},
    }


def test_sync_builds_the_graph_and_reports_ready(synced: Repo, graph_client: GraphClient) -> None:
    assert (synced.status, synced.progress, synced.error) == ("ready", 100, None)
    assert synced.message and synced.message.startswith("2 services, 1 resources, 2 dependencies.")
    edges = _rows(
        graph_client,
        "MATCH (a)-[r:DEPENDS_ON|USES]->(b) RETURN type(r), a.name, b.name, r.source, r.evidence",
    )
    assert sorted(edges) == [
        ["DEPENDS_ON", "web", "api", "declared", "depends_on api in docker-compose.yml"],
        ["USES", "api", "db", "declared", "depends_on db in docker-compose.yml"],
    ]
    tiers = dict(_rows(graph_client, "MATCH (s:Service) RETURN s.name, s.tier"))
    assert tiers == {"api": 1, "web": 3}


def test_authors_are_pseudonymised_and_emails_never_stored(synced: Repo, graph_client: GraphClient) -> None:
    stored = " ".join(
        str(v)
        for in_memory in (False, True)
        for (values,) in _rows(graph_client, "MATCH (n) RETURN [k IN keys(n) | n[k]]", memory=in_memory)
        for v in values
    )
    for name, email in [*PEOPLE, BOT]:
        assert email not in stored and name not in stored
    engineers = _rows(
        graph_client, "MATCH (e:Engineer) RETURN e.handle, e.name, e.pseudonymous ORDER BY e.handle"
    )
    assert len(engineers) == 2 and all(
        h.startswith("dev-") and n.startswith("Contributor ") and p for h, n, p in engineers
    )


def test_display_names_when_pseudonymisation_is_off(
    graph_client: GraphClient, test_repo: Repo, fake_github: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "pseudonymise_authors", False)
    jobs.run_sync(test_repo.id)
    names = {n for (n,) in _rows(graph_client, "MATCH (e:Engineer) RETURN e.name")}
    assert names == {"Ada Realname", "Grace Realname"}
    values = _rows(graph_client, "MATCH (e:Engineer) RETURN [k IN keys(e) | e[k]]")
    assert not [v for (vs,) in values for v in vs if "@" in str(v)]


def test_incidents_come_from_linked_issues_and_fix_commits(synced: Repo, graph_client: GraphClient) -> None:
    rows = _rows(
        graph_client,
        "MATCH (i:Incident) OPTIONAL MATCH (i)-[:AFFECTED]->(s) "
        "RETURN i.id, i.source, i.severity, i.symptom, collect(s.name) ORDER BY i.id",
        memory=True,
    )
    by_id = {r[0]: r for r in rows}
    assert by_id["GH-7"][1:4] == ["github_issue", "sev2", "Steps: open cart"]
    assert sorted(by_id["GH-7"][4]) == ["api", "web"]
    assert "GH-8" not in by_id
    [fix] = [r for r in rows if r[0].startswith("FIX-")]
    assert (fix[1], fix[4]) == ("fix_commit", ["api"])
    assert len(rows) == 2


def test_resync_is_idempotent(synced: Repo, graph_client: GraphClient, test_repo: Repo) -> None:
    before = _counts(graph_client)
    assert registry.claim_for_sync(test_repo.user_id, test_repo.id)
    jobs.run_sync(test_repo.id)
    assert _counts(graph_client) == before
    assert registry.get_any(test_repo.id).status == "ready"  # type: ignore[union-attr]


def test_resync_expires_an_edge_the_repo_no_longer_declares(
    synced: Repo, graph_client: GraphClient, source: Path, test_repo: Repo
) -> None:
    _commit(
        source,
        PEOPLE[0],
        "drop the db dependency",
        {"docker-compose.yml": COMPOSE.replace(", depends_on: [db]", "")},
    )
    jobs.run_sync(test_repo.id)
    live = _rows(
        graph_client, "MATCH (a)-[r:DEPENDS_ON|USES]->(b) WHERE r.valid_to IS NULL RETURN a.name, b.name"
    )
    expired = _rows(
        graph_client, "MATCH (a)-[r:USES]->(b) WHERE r.valid_to IS NOT NULL RETURN a.name, b.name"
    )
    assert (live, expired) == ([["web", "api"]], [["api", "db"]])


def test_repo_without_structure_is_ready_with_a_clear_message(
    graph_client: GraphClient, test_repo: Repo, fake_github: dict[str, Any], source: Path
) -> None:
    for path in ("docker-compose.yml", "web", "api"):
        shutil.rmtree(source / path) if (source / path).is_dir() else (source / path).unlink()
    _commit(source, PEOPLE[0], "docs only", {"README.md": "hi"})
    jobs.run_sync(test_repo.id)
    repo = registry.get_any(test_repo.id)
    assert repo is not None and repo.status == "ready"
    assert repo.message and repo.message.startswith(pipeline.NO_STRUCTURE)


def test_github_issue_failure_degrades_incidents_not_the_sync(
    graph_client: GraphClient, test_repo: Repo, fake_github: dict[str, Any]
) -> None:
    fake_github["issues"] = GitHubError("GitHub API rate limit reached.")
    jobs.run_sync(test_repo.id)
    repo = registry.get_any(test_repo.id)
    assert repo is not None and repo.status == "ready"
    assert "GitHub issues were not imported (GitHub API rate limit reached.)" in (repo.message or "")


def test_repo_that_turned_private_fails_the_sync_with_a_reason(
    graph_client: GraphClient, test_repo: Repo, fake_github: dict[str, Any]
) -> None:
    fake_github["info_error"] = GitHubError("Only public repositories can be connected.")
    jobs.run_sync(test_repo.id)
    repo = registry.get_any(test_repo.id)
    assert repo is not None and (repo.status, repo.error) == (
        "failed",
        "Only public repositories can be connected.",
    )


def test_status_is_visible_through_the_api(synced: Repo, api: Any) -> None:
    data = api.get(f"/api/repos/{synced.id}").json()["data"]
    assert (data["status"], data["progress"]) == ("ready", 100) and data["last_synced_at"].endswith("Z")
    assert len(api.get("/api/services").json()["data"]) == 2


def test_resync_removes_services_the_repo_no_longer_has(
    synced: Repo, graph_client: GraphClient, source: Path, test_repo: Repo
) -> None:
    shutil.rmtree(source / "web")
    _commit(
        source,
        PEOPLE[0],
        "drop the web app",
        {"docker-compose.yml": COMPOSE.replace("  web: {build: ./web, depends_on: [api]}\n", "")},
    )
    jobs.run_sync(test_repo.id)
    assert {n for (n,) in _rows(graph_client, "MATCH (s:Service) RETURN s.name")} == {"api"}
    assert _rows(graph_client, "MATCH (:Service {name: 'web'})-[r]-() RETURN count(r)") == [[0]]
    assert _rows(
        graph_client, "MATCH (i:Incident {id: 'GH-7'})-[:AFFECTED]->(s) RETURN count(s)", memory=True
    ) == [[2]]


def test_git_log_never_needs_file_contents(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[list[str]] = []

    def fake_git(args: list[str], cwd: Path) -> str:
        seen.append(args)
        return ""

    monkeypatch.setattr(git_history, "run_git", fake_git)
    git_history.load_commits(tmp_path)
    assert "--no-renames" in seen[0] and "--name-only" in seen[0]
