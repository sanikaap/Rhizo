import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

_MAX_LIST_ITEMS = 10
_SECRET_KEY = re.compile(r"secret|token|password|api_?key", re.IGNORECASE)


@dataclass(frozen=True)
class QueryRecord:
    name: str
    cypher: str
    params: dict[str, Any]
    ms: float
    rows: int


@dataclass
class QueryScope:
    records: list[QueryRecord] = field(default_factory=list)
    started: float = field(default_factory=perf_counter)

    @property
    def cypher(self) -> list[str]:
        return [r.cypher for r in self.records]

    @property
    def took_ms(self) -> int:
        return round((perf_counter() - self.started) * 1000)


_current: ContextVar[QueryScope | None] = ContextVar("rhizo_querylog", default=None)


@contextmanager
def scope() -> Iterator[QueryScope]:
    qs = QueryScope()
    token = _current.set(qs)
    try:
        yield qs
    finally:
        _current.reset(token)


def record(rec: QueryRecord) -> None:
    qs = _current.get()
    if qs is not None:
        qs.records.append(rec)


def redact(params: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in params.items():
        if _SECRET_KEY.search(key):
            continue
        if isinstance(value, list) and len(value) > _MAX_LIST_ITEMS:
            out[key] = [*value[:_MAX_LIST_ITEMS], f"... {len(value) - _MAX_LIST_ITEMS} more"]
        else:
            out[key] = value
    return out
