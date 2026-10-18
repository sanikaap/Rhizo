import threading
from collections.abc import Callable
from typing import Generic, TypeVar

from falkordb import Graph

from rhizo.graph import queries as Q
from rhizo.graph.client import run, scalar

T = TypeVar("T")


def current(g: Graph) -> int:
    return int(scalar(g, "graph_version", Q.GET_VERSION) or 0)


def bump(g: Graph, now: int) -> int:
    rows = run(g, "bump_graph_version", Q.BUMP_VERSION, {"now": now})
    return int(rows[0][0])


class VersionedCache(Generic[T]):
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], tuple[int, T]] = {}
        self._lock = threading.Lock()

    def get(self, g: Graph, key: str, compute: Callable[[], T]) -> T:
        version = current(g)
        slot = (g.name, key)
        with self._lock:
            hit = self._entries.get(slot)
        if hit is not None and hit[0] == version:
            return hit[1]
        value = compute()
        with self._lock:
            self._entries[slot] = (version, value)
        return value
