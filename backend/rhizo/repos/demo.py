import sqlite3

from rhizo.core.errors import Conflict
from rhizo.repos import jobs, registry
from rhizo.repos.registry import Repo

OWNER = "GoogleCloudPlatform"
NAME = "microservices-demo"


def _create(user_id: str) -> Repo | None:
    try:
        repo = registry.create(user_id, OWNER, NAME, is_demo=True)
    except sqlite3.IntegrityError:
        return None
    jobs.enqueue(repo.id)
    return repo


def provision_on_first_visit(user_id: str) -> Repo | None:
    if not registry.ensure_account(user_id) or registry.demo_dismissed(user_id):
        return None
    return _create(user_id)


def restore(user_id: str) -> Repo:
    registry.set_demo_dismissed(user_id, False)
    existing = registry.demo_for(user_id)
    if existing is not None:
        return existing
    repo = _create(user_id)
    if repo is None:
        raise Conflict(f"{OWNER}/{NAME} is already connected as a regular repository")
    return repo
