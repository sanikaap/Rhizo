import socket
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from rhizo.api.deps import TOKEN_AUDIENCE, TOKEN_ISSUER
from rhizo.config import settings
from rhizo.graph.client import GraphClient, repo_prefix
from rhizo.main import app
from rhizo.repos import jobs, registry
from rhizo.repos.registry import Repo

TEST_SECRET = "test-secret-" + "x" * 32
TEST_USER = "user-123"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    monkeypatch.setattr(settings, "auth_secret", TEST_SECRET)
    monkeypatch.setattr(settings, "registry_path", tmp_path / "registry.db")
    queued: list[str] = []
    monkeypatch.setattr(jobs, "enqueue", queued.append)
    return queued


def make_token(sub: str = TEST_USER, ttl_s: int = 300, secret: str = TEST_SECRET, **overrides: object) -> str:
    now = int(time.time())
    claims = {
        "sub": sub,
        "iss": TOKEN_ISSUER,
        "aud": TOKEN_AUDIENCE,
        "iat": now,
        "exp": now + ttl_s,
        **overrides,
    }
    return jwt.encode(claims, secret, algorithm="HS256")


def client_for(repo: Repo, user: str = TEST_USER) -> TestClient:
    return TestClient(app, headers={"Authorization": f"Bearer {make_token(user)}", "X-Repo-Id": repo.id})


@pytest.fixture
def test_repo() -> Repo:
    return registry.create(TEST_USER, "acme", f"repo-{uuid4().hex[:8]}")


@pytest.fixture
def graph_client(test_repo: Repo) -> Iterator[GraphClient]:
    gc = GraphClient(repo_prefix(test_repo.user_id, test_repo.id))
    yield gc
    gc.drop()


@pytest.fixture
def api(graph_client: GraphClient, test_repo: Repo) -> TestClient:
    return client_for(test_repo)


@pytest.fixture
def anonymous_api(graph_client: GraphClient) -> TestClient:
    return TestClient(app)


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
    return port


@pytest.fixture
def api_db_down(test_repo: Repo, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "falkordb_port", _closed_port())
    return client_for(test_repo)


@pytest.fixture
def tiny_graph(graph_client: GraphClient) -> GraphClient:
    graph_client.topology().query(
        """
        CREATE (a:Service {name: 'A', tier: 1}), (b:Service {name: 'B', tier: 2}),
               (c:Service {name: 'C', tier: 3}), (d:Service {name: 'D', tier: 2}),
               (r:Resource {name: 'R', kind: 'cache'}),
               (a)-[:DEPENDS_ON {source: 'declared', confidence: 0.9, valid_from: 0}]->(b),
               (b)-[:DEPENDS_ON {source: 'inferred', confidence: 0.8, valid_from: 0}]->(c),
               (c)-[:USES {source: 'declared', confidence: 0.95, valid_from: 0}]->(r),
               (d)-[:USES {source: 'inferred', confidence: 0.7, valid_from: 0}]->(r)
        """
    )
    return graph_client
