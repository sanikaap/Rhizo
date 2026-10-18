from typing import Any

import httpx
import pytest

from rhizo.config import settings
from rhizo.core.errors import BadRequest
from rhizo.repos import github, gitops
from rhizo.repos.github import GitHubError, RepoRef


@pytest.mark.parametrize(
    ("url", "owner", "name"),
    [
        (
            "https://github.com/GoogleCloudPlatform/microservices-demo",
            "GoogleCloudPlatform",
            "microservices-demo",
        ),
        ("https://github.com/pallets/flask.git", "pallets", "flask"),
        ("https://github.com/a/b/", "a", "b"),
        ("https://github.com/my-org/repo.name_x", "my-org", "repo.name_x"),
    ],
)
def test_accepts_plain_github_repo_urls(url: str, owner: str, name: str) -> None:
    ref = github.parse_url(url)
    assert (ref.owner, ref.name) == (owner, name)
    assert ref.clone_url == f"https://github.com/{owner}/{name}.git"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "https://gitlab.com/a/b",
        "https://github.com.evil.com/a/b",
        "https://evil.com/github.com/a/b",
        "https://user:pass@github.com/a/b",
        "https://github.com:443/a/b",
        "https://github.com/a/b/tree/main",
        "https://github.com/a/b?x=1",
        "https://github.com/a/b#frag",
        "https://github.com/a",
        "https://github.com/a/..",
        "https://github.com/../etc/passwd",
        "https://github.com/a/b%2F..%2Fc",
        "https://github.com/-a/b",
        "https://github.com/a--b/c",
        "https://github.com/a/b;rm -rf /",
        "https://github.com/a/b\nhttps://evil.com/x",
        "https://github.com/a/-uupload-pack=touch /tmp/pwned",
        "ext::sh -c touch% /tmp/pwned",
        "file:///etc/passwd",
        "git@github.com:a/b.git",
        "https://github.com/a/b.git.git",
        "https://github.com/\uff41/b",
        "",
        "https://github.com/" + "a" * 40 + "/b",
        123,
    ],
)
def test_rejects_everything_else(url: Any) -> None:
    with pytest.raises(BadRequest):
        github.parse_url(url)


class FakeResponse:
    def __init__(self, status: int, body: object = None, headers: dict[str, str] | None = None) -> None:
        self.status_code, self._body, self.headers = status, body, headers or {}

    def json(self) -> object:
        return self._body


def _github(monkeypatch: pytest.MonkeyPatch, response: FakeResponse) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_get(url: str, **kwargs: Any) -> FakeResponse:
        calls.append({"url": url, **kwargs})
        return response

    monkeypatch.setattr(httpx, "get", fake_get)
    return calls


def _repo(**overrides: object) -> dict[str, object]:
    return {
        "full_name": "Acme/App",
        "private": False,
        "visibility": "public",
        "size": 1024,
        "default_branch": "main",
        **overrides,
    }


def test_public_repo_info_uses_canonical_names(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _github(monkeypatch, FakeResponse(200, _repo()))
    info = github.repo_info(RepoRef("acme", "app"))
    assert (info.owner, info.name, info.size_kb) == ("Acme", "App", 1024)
    assert calls[0]["url"] == "https://api.github.com/repos/acme/app"
    assert "Authorization" not in calls[0]["headers"]


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (FakeResponse(200, _repo(private=True)), "Only public"),
        (FakeResponse(200, _repo(visibility="internal")), "Only public"),
        (FakeResponse(404, {}), "not found, or it is private"),
        (FakeResponse(403, {}, {"x-ratelimit-remaining": "0"}), "rate limit"),
        (FakeResponse(200, _repo(size=10**9)), "the limit is"),
    ],
)
def test_private_missing_oversize_and_rate_limited_repos_are_rejected(
    monkeypatch: pytest.MonkeyPatch, response: FakeResponse, message: str
) -> None:
    _github(monkeypatch, response)
    with pytest.raises(GitHubError, match=message):
        github.repo_info(RepoRef("acme", "app"))


def test_optional_token_is_sent_only_to_the_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "github_token", "ghp_test")
    calls = _github(monkeypatch, FakeResponse(200, _repo()))
    github.repo_info(RepoRef("acme", "app"))
    assert calls[0]["headers"]["Authorization"] == "Bearer ghp_test"


@pytest.mark.parametrize(
    "url", ["file:///etc", "ext::sh -c id", "ssh://github.com/a/b.git", "http://github.com/a/b"]
)
def test_git_refuses_every_protocol_but_https(url: str) -> None:
    with pytest.raises(gitops.GitError), gitops.clone(url):
        pass


def test_one_transport_failure_is_retried_but_two_are_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def flaky(url: str, **kwargs: Any) -> FakeResponse:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.RemoteProtocolError("dropped")
        return FakeResponse(200, _repo())

    monkeypatch.setattr(httpx, "get", flaky)
    assert github.repo_info(RepoRef("acme", "app")).name == "App"

    def down(url: str, **kwargs: Any) -> FakeResponse:
        raise httpx.ConnectTimeout("timeout")

    monkeypatch.setattr(httpx, "get", down)
    with pytest.raises(Exception, match="GitHub API unreachable: ConnectTimeout"):
        github.repo_info(RepoRef("acme", "app"))
