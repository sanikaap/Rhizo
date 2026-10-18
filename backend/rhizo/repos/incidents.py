import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from falkordb import Graph

from rhizo.core.timeutil import to_epoch
from rhizo.graph import queries as Q
from rhizo.graph.client import run
from rhizo.ingest.common import write
from rhizo.ingest.git_history import Commit

LABELS = ("bug", "incident")
MAX_FIX_COMMITS = 100
_FIX_SUBJECT = re.compile(r"^(?:(?:fix|fixes|fixed|hotfix|bugfix)(?:\([^)]*\))?!?:|revert\b)", re.IGNORECASE)
_CLOSES = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b", re.IGNORECASE)
_SEV1 = re.compile(r"critical|sev ?1|p0|blocker|outage", re.IGNORECASE)
_SEV2 = re.compile(r"major|sev ?2|p1|high", re.IGNORECASE)
_MAX_SYMPTOM = 200


@dataclass(frozen=True)
class Derived:
    id: str
    title: str
    symptom: str
    severity: str
    started_at: int
    resolved_at: int
    fix: str | None
    source: str
    url: str
    affected: list[str]
    resolved_by: str | None


def _services(commit: Commit, owners: dict[str, str]) -> set[str]:
    return {owners[f] for f in commit.files if f in owners}


def _severity(labels: list[str]) -> str:
    text = " ".join(labels)
    return "sev1" if _SEV1.search(text) else "sev2" if _SEV2.search(text) else "sev3"


def _epoch(iso: str) -> int:
    return to_epoch(datetime.fromisoformat(iso.replace("Z", "+00:00")))


def _symptom(issue: dict[str, Any]) -> str:
    for line in (issue.get("body") or "").splitlines():
        text = line.strip().lstrip("#>*- ").strip()
        if text and not text.startswith(("<!--", "```")):
            return text[:_MAX_SYMPTOM]
    return str(issue.get("title", ""))[:_MAX_SYMPTOM]


def derive(
    repo_url: str, issues: list[dict[str, Any]], commits: list[Commit], owners: dict[str, str]
) -> list[Derived]:
    by_issue: dict[int, list[Commit]] = {}
    for c in commits:
        for number in _CLOSES.findall(c.message):
            by_issue.setdefault(int(number), []).append(c)

    found: list[Derived] = []
    linked_shas: set[str] = set()
    for issue in issues:
        fixes = [c for c in by_issue.get(int(issue["number"]), []) if not c.bot]
        affected = sorted(set().union(*(_services(c, owners) for c in fixes))) if fixes else []
        if not affected:
            continue
        latest = max(fixes, key=lambda c: c.ts)
        linked_shas |= {c.sha for c in fixes}
        labels = [str(lbl.get("name", "")) for lbl in issue.get("labels") or []]
        found.append(
            Derived(
                id=f"GH-{issue['number']}",
                title=str(issue["title"])[:200],
                symptom=_symptom(issue),
                severity=_severity(labels),
                started_at=_epoch(issue["created_at"]),
                resolved_at=_epoch(issue["closed_at"]),
                fix=latest.message[:200],
                source="github_issue",
                url=str(issue["html_url"]),
                affected=affected,
                resolved_by=latest.author.handle if latest.author else None,
            )
        )

    fix_commits = [
        c
        for c in commits
        if not c.bot and c.sha not in linked_shas and _FIX_SUBJECT.match(c.message) and _services(c, owners)
    ]
    for c in sorted(fix_commits, key=lambda c: c.ts, reverse=True)[:MAX_FIX_COMMITS]:
        found.append(
            Derived(
                id=f"FIX-{c.sha[:8]}",
                title=c.message[:200],
                symptom=f"Fixed by commit {c.sha[:8]}",
                severity="sev3",
                started_at=c.ts,
                resolved_at=c.ts,
                fix=c.message[:200],
                source="fix_commit",
                url=f"{repo_url}/commit/{c.sha}",
                affected=sorted(_services(c, owners)),
                resolved_by=c.author.handle if c.author else None,
            )
        )
    return found


def write_incidents(memory: Graph, incidents: list[Derived]) -> int:
    rows = [{**i.__dict__} for i in incidents]
    write(memory, "derived_incidents", Q.UPSERT_DERIVED_INCIDENTS, rows)
    resolved = [{"id": i.id, "handle": i.resolved_by} for i in incidents if i.resolved_by]
    if resolved:
        run(memory, "derived_resolved_by", Q.SET_RESOLVED_BY, {"rows": resolved})
    return len(incidents)
