import re
from dataclasses import dataclass, field
from typing import Literal

from rhizo.graph.scoring import CODE_CONFIDENCE, DECLARED_CONFIDENCE

EdgeType = Literal["DEPENDS_ON", "USES"]
EdgeSource = Literal["declared", "code"]

CONFIDENCE: dict[EdgeSource, float] = {"declared": DECLARED_CONFIDENCE, "code": CODE_CONFIDENCE}
_RANK: dict[EdgeSource, int] = {"declared": 0, "code": 1}

_INVALID = re.compile(r"[^A-Za-z0-9._-]+")


def service_name(raw: str) -> str:
    return _INVALID.sub("-", raw.strip().lstrip("@")).strip("-.")[:64] or "root"


@dataclass
class Service:
    name: str
    path_prefix: str | None = None
    language: str | None = None
    detected_by: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Resource:
    name: str
    kind: str


@dataclass(frozen=True)
class Edge:
    rel: EdgeType
    source: str
    target: str
    provenance: EdgeSource
    evidence: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.rel, self.source, self.target)

    @property
    def confidence(self) -> float:
        return CONFIDENCE[self.provenance]


@dataclass
class Detection:
    services: dict[str, Service] = field(default_factory=dict)
    resources: dict[str, Resource] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)

    def add_service(self, svc: Service) -> None:
        same_dir = next(
            (s for s in self.services.values() if svc.path_prefix and s.path_prefix == svc.path_prefix), None
        )
        if same_dir is not None and same_dir.name != svc.name:
            self.aliases[svc.name] = same_dir.name
            same_dir.detected_by |= svc.detected_by
            same_dir.language = same_dir.language or svc.language
            return
        cur = self.services.get(svc.name)
        if cur is None:
            self.services[svc.name] = svc
            return
        cur.path_prefix = cur.path_prefix or svc.path_prefix
        cur.language = cur.language or svc.language
        cur.detected_by |= svc.detected_by

    def merge(self, other: "Detection") -> None:
        for svc in other.services.values():
            self.add_service(svc)
        for res in other.resources.values():
            self.resources.setdefault(res.name, res)
        self.aliases |= other.aliases
        self.edges += other.edges

    def unique_edges(self) -> list[Edge]:
        best: dict[tuple[str, str, str], Edge] = {}
        known = set(self.services) | set(self.resources)
        for raw in self.edges:
            e = Edge(
                raw.rel,
                self.aliases.get(raw.source, raw.source),
                self.aliases.get(raw.target, raw.target),
                raw.provenance,
                raw.evidence,
            )
            if e.source == e.target or e.source not in self.services or e.target not in known:
                continue
            rel: EdgeType = (
                "USES" if e.target in self.resources and e.target not in self.services else "DEPENDS_ON"
            )
            edge = Edge(rel, e.source, e.target, e.provenance, e.evidence)
            cur = best.get(edge.key)
            if cur is None or _RANK[edge.provenance] < _RANK[cur.provenance]:
                best[edge.key] = edge
        return sorted(best.values(), key=lambda e: e.key)
