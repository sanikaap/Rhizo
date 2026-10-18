import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from falkordb import Graph

from rhizo.config import settings
from rhizo.core.errors import Busy, RhizoError
from rhizo.core.timeutil import now_epoch
from rhizo.detect.model import CONFIDENCE, Detection
from rhizo.detect.run import detect
from rhizo.graph import queries as Q
from rhizo.graph import tiers, version
from rhizo.graph.client import GraphClient, repo_prefix, run
from rhizo.graph.schema import ensure_schema
from rhizo.ingest import cochange, git_history
from rhizo.ingest.common import IngestCounts, expire_edges, write_edges, write_nodes
from rhizo.repos import evaluation, github, gitops, registry
from rhizo.repos import incidents as derived_incidents
from rhizo.repos.github import RepoRef
from rhizo.repos.registry import Status

log = logging.getLogger("rhizo.sync")

_DAY_S = 86_400
NO_STRUCTURE = (
    "No structure detected: no docker-compose files, Kubernetes manifests, or Python/JS packages were found. "
    "Git history was still imported."
)


def _progress(repo_id: str, status: Status, progress: int, message: str) -> None:
    registry.update(repo_id, status=status, progress=progress, message=message)


@contextmanager
def _sync_lock(client: GraphClient) -> Iterator[None]:
    key, token = f"rhizo:{client.prefix}:sync-lock", uuid4().hex
    if not client.try_lock(key, token, settings.sync_lock_ttl_s):
        raise Busy("a sync is already running for this repository")
    try:
        yield
    finally:
        client.unlock(key, token)


def _write_detection(topology: Graph, d: Detection, now: int, repo: str) -> IngestCounts:
    services = [
        {
            "name": s.name,
            "prefix": s.path_prefix,
            "language": s.language,
            "detected_by": sorted(s.detected_by),
        }
        for s in d.services.values()
    ]
    resources = [{"name": r.name, "kind": r.kind} for r in d.resources.values()]
    edges = d.unique_edges()
    run(topology, "detect_delete_vanished", Q.DELETE_VANISHED_NODES, {"names": [*d.services, *d.resources]})
    counts = write_nodes(topology, "detect_services", Q.UPSERT_SERVICES, services)
    counts += write_nodes(topology, "detect_service_details", Q.SET_SERVICE_DETAILS, services, repo=repo)
    counts += write_nodes(topology, "detect_resources", Q.UPSERT_RESOURCES, resources)
    for rel, query in (("DEPENDS_ON", Q.UPSERT_DEPENDS_ON), ("USES", Q.UPSERT_USES)):
        for prov in CONFIDENCE:
            rows = [
                {"source": e.source, "target": e.target, "evidence": e.evidence}
                for e in edges
                if e.rel == rel and e.provenance == prov
            ]
            counts += write_edges(
                topology,
                f"detect_{rel.lower()}_{prov}",
                query,
                rows,
                source=prov,
                confidence=CONFIDENCE[prov],
                now=now,
            )
    seen = [f"{e.rel}:{e.source}->{e.target}" for e in edges]
    return counts + expire_edges(
        topology,
        "detect_expire_vanished",
        Q.EXPIRE_VANISHED_DETECTED,
        seen=seen,
        sources=list(CONFIDENCE),
        now=now,
    )


def _issues(ref: RepoRef) -> tuple[list[dict[str, Any]], str | None]:
    try:
        by_number = {
            i["number"]: i for label in derived_incidents.LABELS for i in github.closed_issues(ref, label)
        }
    except RhizoError as e:
        log.warning("sync %s: issues unavailable (%s)", ref.clone_url, e.message)
        return [], f"GitHub issues were not imported ({e.message})."
    return list(by_number.values()), None


def _summary(d: Detection, edges: int, incidents: int, notes: list[str]) -> str:
    if not d.services:
        parts = [NO_STRUCTURE]
    else:
        parts = [f"{len(d.services)} services, {len(d.resources)} resources, {edges} dependencies."]
    parts.append(
        f"{incidents} incidents from issues and fix commits." if incidents else "No incidents found."
    )
    return " ".join(parts + notes)


def local_demo_checkout() -> Path | None:
    path = settings.demo_repo_path
    return path if (path / ".git").exists() else None


@contextmanager
def _checkout(repo_id: str, repo: registry.Repo, ref: RepoRef) -> Iterator[Path]:
    local = local_demo_checkout() if repo.is_demo else None
    if local is not None:
        _progress(repo_id, "cloning", 10, "Reading the bundled demo repository")
        yield local
        return
    _progress(repo_id, "cloning", 5, "Checking the repository on GitHub")
    github.repo_info(ref)
    _progress(repo_id, "cloning", 10, f"Cloning (partial, up to {settings.git_max_commits} commits)")
    with gitops.clone(ref.clone_url) as checkout:
        yield checkout


def sync(repo_id: str) -> None:
    repo = registry.get_any(repo_id)
    if repo is None:
        return
    client = GraphClient(repo_prefix(repo.user_id, repo.id))
    ref = RepoRef(repo.owner, repo.name)

    with _checkout(repo_id, repo, ref) as checkout:
        _progress(repo_id, "detecting", 35, "Detecting services")
        detection = detect(checkout)
        commits = git_history.load_commits(checkout)
    issues, issue_note = _issues(ref)
    thresholds = cochange.Thresholds(
        min_support=settings.cochange_min_support,
        min_jaccard=settings.cochange_min_jaccard,
        max_files_per_commit=settings.cochange_max_files_per_commit,
        max_services_per_commit=settings.cochange_max_services_per_commit,
    )

    _progress(repo_id, "ingesting", 50, "Writing services and dependencies")
    now = now_epoch()
    prefixes = {s.name: s.path_prefix for s in detection.services.values() if s.path_prefix is not None}
    with _sync_lock(client):
        ensure_schema(client)
        topology = client.topology()
        _write_detection(topology, detection, now, repo.full_name)
        _progress(repo_id, "ingesting", 65, "Importing git history")
        git_history.ingest(topology, commits, prefixes)
        _progress(repo_id, "ingesting", 75, "Mining co-change")
        cochange.ingest(topology, now, thresholds)
        cutoff = now - settings.edge_expiry_days * _DAY_S
        expire_edges(topology, "expire_stale_inferred", Q.EXPIRE_STALE_INFERRED, cutoff=cutoff, now=now)
        _progress(repo_id, "ingesting", 85, "Deriving tiers and incidents")
        tiers.assign(topology)
        owners = git_history.file_owner({f for c in commits for f in c.files}, prefixes)
        found = derived_incidents.derive(
            f"https://github.com/{ref.owner}/{ref.name}", issues, commits, owners
        )
        derived_incidents.write_incidents(client.memory(), found)
        version.bump(topology, now)
    _progress(repo_id, "ingesting", 95, "Running the held-out evaluation")
    registry.save_evaluation(repo_id, evaluation.evaluate(detection, commits, thresholds).model_dump_json())

    message = _summary(
        detection, len(detection.unique_edges()), len(found), [issue_note] if issue_note else []
    )
    registry.update(repo_id, status="ready", progress=100, message=message, error=None, last_synced_at=now)
    log.info("sync %s/%s: %s", repo.owner, repo.name, message)
