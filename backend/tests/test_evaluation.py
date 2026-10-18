from collections.abc import Sequence

from rhizo.detect.model import Detection, Edge, Service
from rhizo.ingest.cochange import Thresholds
from rhizo.ingest.git_history import Author, Commit
from rhizo.repos.evaluation import evaluate

T = Thresholds(min_support=3, min_jaccard=0.25, max_files_per_commit=30, max_services_per_commit=4)
DEV = Author("dev-1", "Contributor 1")


def _detection() -> Detection:
    d = Detection()
    for name in ("a", "b", "c", "d"):
        d.add_service(Service(name=name, path_prefix=f"{name}/"))
    d.edges.append(Edge("DEPENDS_ON", "a", "b", "declared", "compose"))
    d.edges.append(Edge("DEPENDS_ON", "c", "d", "declared", "compose"))
    return d


def _commits(services_per_commit: Sequence[tuple[str, ...]]) -> list[Commit]:
    return [
        Commit(f"{i:040x}", 1_700_000_000 + i, "m", tuple(f"{s}/f.py" for s in services), DEV, False)
        for i, services in enumerate(services_per_commit)
    ]


def test_scores_come_from_the_held_out_commits_only() -> None:
    train = [("a", "c")] * 10 + [("a",)] * 10 + [("b",)] * 12
    test = [("a", "c")] * 3 + [("a", "b")] * 2 + [("b", "d")] * 1 + [("a",)] * 2
    result = evaluate(_detection(), _commits(train + test), T)

    assert result.status == "ok"
    assert (result.commits_eligible, result.train_commits, result.test_commits) == (40, 32, 8)
    assert result.truth_pairs == 3
    declared, rhizo = result.systems
    assert (declared.predicted, declared.hits, declared.precision, declared.recall) == (2, 1, 0.5, 0.333)
    assert (rhizo.predicted, rhizo.hits, rhizo.precision, rhizo.recall) == (3, 2, 0.667, 0.667)
    assert [(p.a, p.b) for p in result.hidden_hits] == [("a", "c")]


def test_bots_and_bulk_commits_are_not_counted() -> None:
    commits = _commits([("a", "c")] * 40)
    bot = [Commit(c.sha, c.ts, c.message, c.files, None, True) for c in commits]
    result = evaluate(_detection(), bot, T)
    assert result.status == "insufficient_history"
    assert result.commits_eligible == 0


def test_thin_history_is_reported_not_scored() -> None:
    result = evaluate(_detection(), _commits([("a", "b")] * 10), T)
    assert result.status == "insufficient_history"
    assert result.reason and "Only 10 commits" in result.reason
    assert result.systems == []


def test_single_service_repo_has_nothing_to_predict() -> None:
    d = Detection()
    d.add_service(Service(name="only", path_prefix=""))
    result = evaluate(d, _commits([("x",)] * 50), T)
    assert result.status == "insufficient_history"
