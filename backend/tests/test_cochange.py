from rhizo.graph.client import GraphClient, run
from rhizo.ingest import cochange
from rhizo.ingest.cochange import Pair, Thresholds, mine

T = Thresholds(min_support=3, min_jaccard=0.25, max_files_per_commit=30, max_services_per_commit=4)


def test_pairs_need_both_support_and_jaccard() -> None:
    assert mine([{"a", "b"}] * 3, T) == [Pair("a", "b", 3, 1.0)]
    assert mine([{"a", "b"}] * 2, T) == []
    assert mine([{"a", "b"}] * 3 + [{"a"}] * 9, T) == [Pair("a", "b", 3, 0.25)]
    assert mine([{"a", "b"}] * 3 + [{"a"}] * 10, T) == []


def test_cross_cutting_commits_are_ignored() -> None:
    everything = {"a", "b", "c", "d", "e"}
    assert mine([everything] * 10, T) == []
    assert mine([{"a", "b", "c", "d"}] * 3, T) != []


def _commit(gc: GraphClient, sha: str, services: list[str], files_count: int = 2, bot: bool = False) -> None:
    gc.topology().query(
        """
        MERGE (c:Commit {sha: $sha}) SET c.files_count = $files_count, c.bot = $bot
        WITH c UNWIND $services AS name
        MERGE (s:Service {name: name})
        MERGE (f:File {path: 'src/' + name + '/main.go'})
        MERGE (f)-[:PART_OF]->(s)
        MERGE (c)-[:TOUCHED]->(f)
        """,
        {"sha": sha, "services": services, "files_count": files_count, "bot": bot},
    )


def _co_change_edges(gc: GraphClient) -> list[list[object]]:
    return run(
        gc.topology(),
        "t_cochange",
        "MATCH (a)-[r:CO_CHANGES_WITH]->(b) RETURN a.name, b.name, r.support, r.confidence, r.valid_to",
    )


def test_ingest_writes_edges_and_skips_bulk_and_bot_commits(graph_client: GraphClient) -> None:
    for i in range(3):
        _commit(graph_client, f"good{i}", ["x", "y"])
    for i in range(5):
        _commit(graph_client, f"bulk{i}", ["y", "z"], files_count=31)
        _commit(graph_client, f"bot{i}", ["x", "z"], bot=True)

    result = cochange.ingest(graph_client.topology(), now=100, t=T)
    assert result.edges_created == 1
    assert _co_change_edges(graph_client) == [["x", "y", 3, 0.8, None]]

    again = cochange.ingest(graph_client.topology(), now=200, t=T)
    assert (again.edges_created, again.edges_updated) == (0, 1)


def test_pair_that_drops_below_threshold_is_expired_not_deleted(graph_client: GraphClient) -> None:
    for i in range(3):
        _commit(graph_client, f"good{i}", ["x", "y"])
    cochange.ingest(graph_client.topology(), now=100, t=T)

    stricter = Thresholds(min_support=4, min_jaccard=0.25, max_files_per_commit=30, max_services_per_commit=4)
    result = cochange.ingest(graph_client.topology(), now=200, t=stricter)
    assert result.edges_expired == 1
    assert _co_change_edges(graph_client) == [["x", "y", 3, 0.8, 200]]
