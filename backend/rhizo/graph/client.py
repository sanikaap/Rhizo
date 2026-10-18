import logging
import threading
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from falkordb import FalkorDB, Graph
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from rhizo.config import settings
from rhizo.core import querylog
from rhizo.core.errors import UpstreamError

log = logging.getLogger("rhizo.cypher")

_UNREACHABLE = (RedisConnectionError, RedisTimeoutError, ConnectionError, OSError)

Row = list[Any]

_RELEASE_LOCK = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end return 0"


_pool: dict[tuple[str, int, str], FalkorDB] = {}
_pool_lock = threading.Lock()


def _connection(host: str, port: int, password: str, connect_timeout_s: float) -> FalkorDB:
    key = (host, port, password)
    with _pool_lock:
        db = _pool.get(key)
        if db is None:
            try:
                db = FalkorDB(
                    host=host,
                    port=port,
                    password=password or None,
                    socket_connect_timeout=connect_timeout_s,
                    socket_timeout=settings.query_timeout_ms / 1000 + 1,
                )
            except _UNREACHABLE as e:
                raise UpstreamError("FalkorDB unreachable") from e
            _pool[key] = db
        return db


def close_all() -> None:
    with _pool_lock:
        for db in _pool.values():
            db.connection.close()
        _pool.clear()


class GraphClient:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix

    @property
    def topology_name(self) -> str:
        return self.prefix

    @property
    def memory_name(self) -> str:
        return f"{self.prefix}_memory"

    def _connect(self) -> FalkorDB:
        s = settings
        return _connection(s.falkordb_host, s.falkordb_port, s.falkordb_password, s.connect_timeout_s)

    def topology(self) -> Graph:
        return self._connect().select_graph(self.topology_name)

    def memory(self) -> Graph:
        return self._connect().select_graph(self.memory_name)

    def redis(self) -> Redis:
        conn: Redis = self._connect().connection
        return conn

    def try_lock(self, key: str, token: str, ttl_s: int) -> bool:
        try:
            return bool(self.redis().set(key, token, nx=True, ex=ttl_s))
        except _UNREACHABLE as e:
            raise UpstreamError("FalkorDB unreachable") from e

    def unlock(self, key: str, token: str) -> None:
        try:
            self.redis().eval(_RELEASE_LOCK, 1, key, token)
        except _UNREACHABLE as e:
            raise UpstreamError("FalkorDB unreachable") from e

    def drop(self) -> None:
        try:
            db = self._connect()
            existing = set(db.list_graphs())
            for name in (self.topology_name, self.memory_name):
                if name in existing:
                    db.select_graph(name).delete()
        except _UNREACHABLE as e:
            raise UpstreamError("FalkorDB unreachable") from e


def ping() -> bool:
    try:
        s = settings
        return bool(
            _connection(
                s.falkordb_host, s.falkordb_port, s.falkordb_password, s.connect_timeout_s
            ).connection.ping()
        )
    except (UpstreamError, *_UNREACHABLE):
        return False


def repo_prefix(user_id: str, repo_id: str) -> str:
    return f"r_{user_id}_{repo_id}"


@dataclass(frozen=True)
class WriteResult:
    rows: list[Row]
    nodes_created: int
    relationships_created: int


def _execute(g: Graph, name: str, cypher: str, params: dict[str, Any]) -> Any:
    t0 = perf_counter()
    try:
        res = g.query(cypher, params, timeout=settings.query_timeout_ms)
    except _UNREACHABLE as e:
        raise UpstreamError("FalkorDB unreachable") from e
    ms = round((perf_counter() - t0) * 1000, 1)
    rows = len(res.result_set)
    querylog.record(
        querylog.QueryRecord(name=name, cypher=cypher, params=querylog.redact(params), ms=ms, rows=rows)
    )
    log.info("cypher %s %.1fms rows=%d", name, ms, rows)
    return res


def run(g: Graph, name: str, cypher: str, params: dict[str, Any] | None = None) -> list[Row]:
    rows: list[Row] = _execute(g, name, cypher, params or {}).result_set
    return rows


def run_write(g: Graph, name: str, cypher: str, params: dict[str, Any] | None = None) -> WriteResult:
    res = _execute(g, name, cypher, params or {})
    return WriteResult(
        rows=res.result_set,
        nodes_created=int(res.nodes_created),
        relationships_created=int(res.relationships_created),
    )


def scalar(g: Graph, name: str, cypher: str, params: dict[str, Any] | None = None) -> Any:
    rows = run(g, name, cypher, params)
    return rows[0][0] if rows and rows[0] else None
