import hashlib
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from falkordb import Graph

from rhizo.config import settings
from rhizo.graph import queries as Q
from rhizo.ingest.common import IngestCounts, write_edges, write_nodes
from rhizo.repos.gitops import run_git

log = logging.getLogger("rhizo.ingest.git")

_SEP = "\x1f"
_COMMIT_MARK = "__C__"
_LOG_FORMAT = f"{_COMMIT_MARK}%H{_SEP}%at{_SEP}%ae{_SEP}%an{_SEP}%s"
_BOT = re.compile(r"\[bot\]|renovate|dependabot|github-actions", re.IGNORECASE)
_SLUG = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class Author:
    handle: str
    name: str


@dataclass(frozen=True)
class Commit:
    sha: str
    ts: int
    message: str
    files: tuple[str, ...]
    author: Author | None
    bot: bool


def author(email: str, name: str) -> Author:
    key = hashlib.sha256((email.strip().lower() or name.strip()).encode()).hexdigest()
    if settings.pseudonymise_authors:
        return Author(handle=f"dev-{key[:8]}", name=f"Contributor {key[:4]}")
    slug = _SLUG.sub("-", name.strip().lower()).strip("-")[:40] or "dev"
    return Author(handle=f"{slug}-{key[:6]}", name=name.strip()[:80] or slug)


def parse_log(text: str) -> list[Commit]:
    commits: list[Commit] = []
    header: list[str] | None = None
    files: list[str] = []

    def flush() -> None:
        if header is None or len(header) != 5:
            return
        sha, ts, email, name, subject = header
        bot = bool(_BOT.search(email) or _BOT.search(name))
        commits.append(Commit(sha, int(ts), subject, tuple(files), None if bot else author(email, name), bot))

    for line in text.splitlines():
        if line.startswith(_COMMIT_MARK):
            flush()
            header, files = line[len(_COMMIT_MARK) :].split(_SEP, 4), []
        elif line.strip():
            files.append(line.strip())
    flush()
    return commits


def load_commits(repo: Path) -> list[Commit]:
    text = run_git(
        [
            "log",
            "--no-merges",
            f"--max-count={settings.git_max_commits}",
            "--name-only",
            "--no-renames",
            f"--pretty=format:{_LOG_FORMAT}",
        ],
        cwd=repo,
    )
    commits = parse_log(text)
    log.info("git: %d commits (%d bots)", len(commits), sum(c.bot for c in commits))
    return commits


def file_owner(paths: set[str], prefixes: dict[str, str]) -> dict[str, str]:
    ordered = sorted(prefixes.items(), key=lambda kv: len(kv[1]), reverse=True)
    owners = {}
    for path in paths:
        service = next((s for s, prefix in ordered if path.startswith(prefix)), None)
        if service:
            owners[path] = service
    return owners


def _committed_to(commits: list[Commit], owners: dict[str, str]) -> list[dict[str, Any]]:
    count: dict[tuple[str, str], int] = defaultdict(int)
    last_at: dict[tuple[str, str], int] = {}
    for c in commits:
        if c.author is None:
            continue
        for service in {owners[f] for f in c.files if f in owners}:
            key = (c.author.handle, service)
            count[key] += 1
            last_at[key] = max(last_at.get(key, 0), c.ts)
    return [
        {"handle": h, "service": s, "count": n, "last_at": last_at[h, s]}
        for (h, s), n in sorted(count.items())
    ]


def ingest(topology: Graph, commits: list[Commit], prefixes: dict[str, str]) -> IngestCounts:
    paths = {f for c in commits for f in c.files}
    owners = file_owner(paths, prefixes)
    authors = {c.author.handle: c.author for c in commits if c.author}
    commit_rows = [
        {"sha": c.sha, "ts": c.ts, "message": c.message, "files_count": len(c.files), "bot": c.bot}
        for c in commits
    ]
    return (
        write_nodes(topology, "git_commits", Q.UPSERT_COMMITS, commit_rows)
        + write_nodes(topology, "git_files", Q.UPSERT_FILES, [{"path": p} for p in sorted(paths)])
        + write_nodes(
            topology,
            "git_engineers",
            Q.UPSERT_ENGINEERS,
            [
                {"handle": a.handle, "name": a.name, "pseudonymous": settings.pseudonymise_authors}
                for a in authors.values()
            ],
        )
        + write_edges(
            topology,
            "git_part_of",
            Q.UPSERT_PART_OF,
            [{"path": p, "service": s} for p, s in sorted(owners.items())],
        )
        + write_edges(
            topology,
            "git_touched",
            Q.UPSERT_TOUCHED,
            [{"sha": c.sha, "path": f} for c in commits for f in set(c.files)],
        )
        + write_edges(
            topology,
            "git_authored",
            Q.UPSERT_AUTHORED,
            [{"handle": c.author.handle, "sha": c.sha} for c in commits if c.author],
        )
        + write_edges(topology, "git_committed_to", Q.SET_COMMITTED_TO, _committed_to(commits, owners))
    )
