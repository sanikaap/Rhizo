import time

import jwt
import pytest
from fastapi.testclient import TestClient

from rhizo.config import settings
from tests.conftest import TEST_USER, make_token

PROTECTED = [
    ("GET", "/api/graph", None),
    ("GET", "/api/services", None),
    ("GET", "/api/incidents", None),
    ("GET", "/api/rankings", None),
    ("POST", "/api/impact/blast-radius", {"service": "C"}),
    ("POST", "/api/agent/ask", {"question": "What breaks if C fails?"}),
    ("GET", "/api/repos", None),
    ("POST", "/api/repos", {"url": "https://github.com/acme/app"}),
    ("POST", "/api/repos/0123456789ab/sync", None),
]


def _send(client: TestClient, method: str, path: str, body: object, token: str | None = None) -> int:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    res = client.request(method, path, json=body, headers=headers)
    if res.status_code == 401:
        assert res.json()["error"]["code"] == "UNAUTHENTICATED"
        assert res.headers["www-authenticate"] == "Bearer"
    return res.status_code


@pytest.mark.parametrize(("method", "path", "body"), PROTECTED)
def test_protected_routes_reject_requests_without_a_token(
    anonymous_api: TestClient, method: str, path: str, body: object
) -> None:
    assert _send(anonymous_api, method, path, body) == 401


def test_health_needs_no_token(anonymous_api: TestClient) -> None:
    assert anonymous_api.get("/api/health").status_code == 200


def test_valid_token_is_accepted(api: TestClient, tiny_graph: object) -> None:
    assert api.get("/api/graph").status_code == 200


def test_expired_token_is_rejected(anonymous_api: TestClient) -> None:
    expired = make_token(iat=int(time.time()) - 3600, exp=int(time.time()) - 60)
    res = anonymous_api.get("/api/graph", headers={"Authorization": f"Bearer {expired}"})
    assert (res.status_code, res.json()["error"]) == (
        401,
        {"code": "UNAUTHENTICATED", "message": "token expired"},
    )


@pytest.mark.parametrize(
    "token",
    [
        make_token(secret="another-secret-" + "y" * 32),
        make_token(aud="someone-else"),
        make_token(iss="evil"),
        jwt.encode(
            {"sub": TEST_USER, "exp": int(time.time()) + 60}, "test-secret-" + "x" * 32, algorithm="HS256"
        ),
        jwt.encode({"sub": TEST_USER}, key="", algorithm="none"),
        "not-a-jwt",
    ],
    ids=["wrong_key", "wrong_audience", "wrong_issuer", "missing_claims", "alg_none", "garbage"],
)
def test_forged_or_malformed_tokens_are_rejected(anonymous_api: TestClient, token: str) -> None:
    assert _send(anonymous_api, "GET", "/api/graph", None, token) == 401


def test_missing_server_secret_fails_closed(
    anonymous_api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "auth_secret", "")
    res = anonymous_api.get("/api/graph", headers={"Authorization": f"Bearer {make_token()}"})
    assert (res.status_code, res.json()["error"]["code"]) == (500, "INTERNAL")


def test_short_secret_is_a_configuration_error() -> None:
    with pytest.raises(ValueError, match="at least 32"):
        type(settings)(auth_secret="short")
