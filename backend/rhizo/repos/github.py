import re
from dataclasses import dataclass
from typing import Any

import httpx

from rhizo.config import settings
from rhizo.core.errors import BadRequest, RhizoError

_URL = re.compile(
    r"^https://github\.com/"
    r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38})/"
    r"(?P<name>[A-Za-z0-9._-]{1,100}?)(?:\.git)?/?$"
)
_API = "https://api.github.com"
_TIMEOUT_S = 15.0


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}.git"


@dataclass(frozen=True)
class RepoInfo:
    owner: str
    name: str
    size_kb: int
    default_branch: str


class GitHubError(RhizoError):
    status, code = 400, "BAD_REQUEST"


def parse_url(url: object) -> RepoRef:
    if not isinstance(url, str) or len(url) > 200:
        raise BadRequest("Use a GitHub URL like https://github.com/owner/repo")
    m = _URL.fullmatch(url.strip())
    if not m or m["name"] in {".", ".."} or m["name"].endswith(".git"):
        raise BadRequest("Use a GitHub URL like https://github.com/owner/repo")
    return RepoRef(m["owner"], m["name"])


def _headers() -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if settings.github_token:
        h["Authorization"] = f"Bearer {settings.github_token}"
    return h


_ATTEMPTS = 2


def _get(path: str, params: dict[str, Any] | None = None) -> httpx.Response:
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            return httpx.get(f"{_API}{path}", headers=_headers(), params=params, timeout=_TIMEOUT_S)
        except httpx.TransportError as e:
            if attempt == _ATTEMPTS:
                raise RhizoError(f"GitHub API unreachable: {type(e).__name__}") from e
    raise AssertionError("unreachable")


def _check(res: httpx.Response, what: str) -> None:
    if res.status_code == 404:
        raise GitHubError(f"{what} not found, or it is private. Only public repositories can be connected.")
    if res.status_code in (403, 429) and res.headers.get("x-ratelimit-remaining") == "0":
        raise GitHubError("GitHub API rate limit reached. Try again later or set GITHUB_TOKEN on the server.")
    if res.status_code >= 400:
        raise GitHubError(f"GitHub API error {res.status_code} for {what}")


def repo_info(ref: RepoRef) -> RepoInfo:
    res = _get(f"/repos/{ref.owner}/{ref.name}")
    _check(res, f"{ref.owner}/{ref.name}")
    data = res.json()
    if data.get("private") or data.get("visibility", "public") != "public":
        raise GitHubError("Only public repositories can be connected.")
    size_kb = int(data.get("size") or 0)
    if size_kb > settings.max_repo_size_mb * 1024:
        raise GitHubError(f"Repository is {size_kb // 1024} MB; the limit is {settings.max_repo_size_mb} MB.")
    owner, name = data["full_name"].split("/", 1)
    return RepoInfo(
        owner=owner, name=name, size_kb=size_kb, default_branch=data.get("default_branch", "main")
    )


def closed_issues(ref: RepoRef, label: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for page in range(1, settings.github_max_issue_pages + 1):
        res = _get(
            f"/repos/{ref.owner}/{ref.name}/issues",
            {"state": "closed", "labels": label, "per_page": 100, "page": page, "sort": "updated"},
        )
        _check(res, f"issues of {ref.owner}/{ref.name}")
        batch = res.json()
        issues += [i for i in batch if "pull_request" not in i]
        if len(batch) < 100:
            break
    return issues
