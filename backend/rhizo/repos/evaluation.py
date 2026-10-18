from itertools import combinations

from rhizo.core.timeutil import now_epoch, to_iso
from rhizo.detect.model import Detection
from rhizo.ingest import cochange
from rhizo.ingest.git_history import Commit, file_owner
from rhizo.models import Evaluation, PairOut, SystemScore

TEST_SHARE = 0.2
MIN_ELIGIBLE_COMMITS = 30
MIN_TRUTH_PAIRS = 1

Pairs = set[tuple[str, str]]


def _pairs(services: set[str]) -> Pairs:
    return set(combinations(sorted(services), 2))


def _score(name: str, predicted: Pairs, truth: Pairs) -> SystemScore:
    hits = len(predicted & truth)
    return SystemScore(
        name=name,
        predicted=len(predicted),
        hits=hits,
        precision=round(hits / len(predicted), 3) if predicted else None,
        recall=round(hits / len(truth), 3) if truth else None,
    )


def _insufficient(reason: str, total: int, eligible: int, train: int = 0, test: int = 0) -> Evaluation:
    return Evaluation(
        status="insufficient_history",
        reason=reason,
        commits_total=total,
        commits_eligible=eligible,
        train_commits=train,
        test_commits=test,
        split_at=None,
        truth_pairs=0,
        systems=[],
        hidden_hits=[],
        created_at=to_iso(now_epoch()) or "",
    )


def evaluate(detection: Detection, commits: list[Commit], t: cochange.Thresholds) -> Evaluation:
    prefixes = {s.name: s.path_prefix for s in detection.services.values() if s.path_prefix is not None}
    owners = file_owner({f for c in commits for f in c.files}, prefixes)
    rows = []
    for c in sorted(commits, key=lambda c: (c.ts, c.sha)):
        if c.bot or len(c.files) > t.max_files_per_commit:
            continue
        services = {owners[f] for f in c.files if f in owners}
        if 0 < len(services) <= t.max_services_per_commit:
            rows.append((c.ts, services))
    total, eligible = len(commits), len(rows)
    if len(prefixes) < 2:
        return _insufficient(
            "Fewer than two services were detected, so there are no pairs to predict.", total, eligible
        )
    if eligible < MIN_ELIGIBLE_COMMITS:
        return _insufficient(
            f"Only {eligible} commits touch detected services; at least {MIN_ELIGIBLE_COMMITS} are needed.",
            total,
            eligible,
        )
    cut = eligible - max(1, round(eligible * TEST_SHARE))
    train, test = rows[:cut], rows[cut:]
    truth: Pairs = set().union(*(_pairs(s) for _, s in test))
    if len(truth) < MIN_TRUTH_PAIRS:
        return _insufficient(
            "No commit in the held-out 20% changed two services together, so there is nothing to predict.",
            total,
            eligible,
            len(train),
            len(test),
        )
    service_names = set(detection.services)
    declared: Pairs = {
        (min(e.source, e.target), max(e.source, e.target))
        for e in detection.unique_edges()
        if e.source in service_names and e.target in service_names and e.source != e.target
    }
    hidden: Pairs = {(p.a, p.b) for p in cochange.mine([s for _, s in train], t)}
    rhizo = declared | hidden
    return Evaluation(
        status="ok",
        reason=None,
        commits_total=total,
        commits_eligible=eligible,
        train_commits=len(train),
        test_commits=len(test),
        split_at=to_iso(test[0][0]),
        truth_pairs=len(truth),
        systems=[
            _score("Declared edges only", declared, truth),
            _score("Rhizo (declared + hidden)", rhizo, truth),
        ],
        hidden_hits=[PairOut(a=a, b=b) for a, b in sorted((hidden - declared) & truth)],
        created_at=to_iso(now_epoch()) or "",
    )
