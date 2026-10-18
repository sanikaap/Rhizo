import logging

from falkordb import Graph
from redis.exceptions import ResponseError

from rhizo.graph import queries as Q
from rhizo.graph.client import GraphClient, run

log = logging.getLogger("rhizo")

_ALREADY_INDEXED = "already indexed"


def _create_indexes(g: Graph, statements: tuple[str, ...]) -> None:
    for cypher in statements:
        try:
            run(g, "create_index", cypher)
        except ResponseError as e:
            if _ALREADY_INDEXED not in str(e):
                raise


def ensure_schema(client: GraphClient) -> None:
    _create_indexes(client.topology(), Q.TOPOLOGY_INDEXES)
    _create_indexes(client.memory(), Q.MEMORY_INDEXES)
    log.info("schema ready for %s", client.prefix)
