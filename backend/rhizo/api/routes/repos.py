import sqlite3

from fastapi import APIRouter
from pydantic import BaseModel

from rhizo.api.deps import User, envelope
from rhizo.core import querylog
from rhizo.core.errors import BadRequest, Conflict, NotFound
from rhizo.core.timeutil import to_iso
from rhizo.graph.client import GraphClient, repo_prefix
from rhizo.models import ConnectRepo, Envelope, RepoOut
from rhizo.repos import demo, github, jobs, registry
from rhizo.repos.registry import RUNNING, Repo

router = APIRouter(prefix="/repos", tags=["repos"])

MAX_REPOS_PER_USER = 10


def _out(repo: Repo) -> RepoOut:
    return RepoOut(
        id=repo.id,
        owner=repo.owner,
        name=repo.name,
        full_name=repo.full_name,
        url=f"https://github.com/{repo.full_name}",
        status=repo.status,
        progress=repo.progress,
        message=repo.message,
        error=repo.error,
        last_synced_at=to_iso(repo.last_synced_at),
        created_at=to_iso(repo.created_at) or "",
        is_demo=repo.is_demo,
    )


def _owned(user: str, repo_id: str) -> Repo:
    repo = registry.get(user, repo_id)
    if repo is None:
        raise NotFound("repository not found")
    return repo


class Deleted(BaseModel):
    deleted: str


@router.post("", status_code=201)
def connect(body: ConnectRepo, user: User) -> Envelope[RepoOut]:
    ref = github.parse_url(body.url)
    if len(registry.list_for(user)) >= MAX_REPOS_PER_USER:
        raise BadRequest(f"you can connect at most {MAX_REPOS_PER_USER} repositories")
    info = github.repo_info(ref)
    try:
        repo = registry.create(user, info.owner, info.name)
    except sqlite3.IntegrityError as e:
        raise Conflict(f"{info.owner}/{info.name} is already connected") from e
    jobs.enqueue(repo.id)
    return envelope(_out(repo), querylog.QueryScope())


@router.get("")
def list_repos(user: User) -> Envelope[list[RepoOut]]:
    demo.provision_on_first_visit(user)
    return envelope([_out(r) for r in registry.list_for(user)], querylog.QueryScope())


@router.post("/demo", status_code=201)
def load_demo(user: User) -> Envelope[RepoOut]:
    return envelope(_out(demo.restore(user)), querylog.QueryScope())


@router.get("/{repo_id}")
def get_repo(repo_id: str, user: User) -> Envelope[RepoOut]:
    return envelope(_out(_owned(user, repo_id)), querylog.QueryScope())


@router.post("/{repo_id}/sync", status_code=202)
def sync(repo_id: str, user: User) -> Envelope[RepoOut]:
    _owned(user, repo_id)
    if not registry.claim_for_sync(user, repo_id):
        raise Conflict("a sync is already queued or running")
    jobs.enqueue(repo_id)
    return envelope(_out(_owned(user, repo_id)), querylog.QueryScope())


@router.delete("/{repo_id}")
def delete(repo_id: str, user: User) -> Envelope[Deleted]:
    repo = _owned(user, repo_id)
    if repo.status in RUNNING:
        raise Conflict("wait for the running sync to finish before deleting")
    GraphClient(repo_prefix(repo.user_id, repo.id)).drop()
    registry.delete(user, repo_id)
    if repo.is_demo:
        registry.set_demo_dismissed(user, True)
    return envelope(Deleted(deleted=repo_id), querylog.QueryScope())
