from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

from rhizo.core.validate import MAX_HOPS, MIN_HOPS, FilePath, Name

T = TypeVar("T")

Provenance = Literal["declared", "code", "observed", "inferred"]
Basis = Literal["declared", "code", "observed", "inferred", "connectivity_fallback", "n/a"]
NodeLabel = Literal["Service", "Resource", "Engineer", "Team", "File", "Incident", "Runbook"]
PropertyValue = str | int | float | bool | None


def _omit_none(v: object) -> bool:
    return v is None


class Meta(BaseModel):
    basis: Basis
    took_ms: int
    cypher: list[str]


class Envelope(BaseModel, Generic[T]):
    data: T
    meta: Meta


class GraphCounts(BaseModel):
    services: int
    edges: int
    incidents: int


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    falkordb: Literal["up", "down"]
    graph_counts: GraphCounts


class GraphNode(BaseModel):
    id: str
    label: NodeLabel
    name: str
    properties: dict[str, PropertyValue]
    risk_score: int | None = Field(default=None, exclude_if=_omit_none)


class ImpactItem(BaseModel):
    service: GraphNode
    hops: int
    path: list[str]
    path_confidence: float
    basis: Basis


class BlastRadiusRequest(BaseModel):
    service: Name
    max_hops: int = Field(default=4, ge=MIN_HOPS, le=MAX_HOPS)
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    as_of: datetime | None = None


class BlastRadius(BaseModel):
    service: str
    items: list[ImpactItem]
    risk_score: int


class WhatIfRequest(BaseModel):
    services: list[Name] = Field(min_length=1, max_length=20)
    max_hops: int = Field(default=4, ge=MIN_HOPS, le=MAX_HOPS)


class WhatIf(BaseModel):
    failed: list[str]
    items: list[ImpactItem]
    risk_score: int


class UpstreamSuspectsRequest(BaseModel):
    service: Name
    max_hops: int = Field(default=3, ge=MIN_HOPS, le=MAX_HOPS)


class Suspect(BaseModel):
    service: GraphNode
    hops: int
    recent_commits: int
    score: float


class UpstreamSuspects(BaseModel):
    service: str
    suspects: list[Suspect]


EdgeType = Literal["DEPENDS_ON", "USES", "CO_CHANGES_WITH", "OWNS", "COMMITTED_TO"]


class GraphEdge(BaseModel):
    id: str
    source_id: str
    target_id: str
    type: EdgeType
    provenance: Provenance
    confidence: float
    valid_from: str | None
    valid_to: str | None
    evidence: str | None = Field(default=None, exclude_if=_omit_none)


class GraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class Responder(BaseModel):
    engineer: GraphNode
    score: float
    reason: str


class ServiceDetail(BaseModel):
    node: GraphNode
    owners: list[GraphNode]
    upstream: list[ImpactItem]
    blast_radius_count: int
    responders: list[Responder]
    resources: list[GraphNode]


class HiddenDependency(BaseModel):
    id: str
    kind: Literal["shared_resource", "co_change"]
    a: GraphNode
    b: GraphNode
    via: GraphNode | None = Field(default=None, exclude_if=_omit_none)
    confidence: float
    support: int | None = Field(default=None, exclude_if=_omit_none)
    jaccard: float | None = Field(default=None, exclude_if=_omit_none)
    evidence: str


RankingMetric = Literal["pagerank", "centrality", "community"]


class RankingItem(BaseModel):
    service: GraphNode
    score: float
    community: int | None = Field(default=None, exclude_if=_omit_none)


class Rankings(BaseModel):
    metric: RankingMetric
    algorithm: Literal["falkordb", "degree_fallback"]
    items: list[RankingItem]


Severity = Literal["sev1", "sev2", "sev3"]


class Incident(BaseModel):
    id: str
    title: str
    symptom: str
    severity: Severity
    status: Literal["open", "resolved"]
    started_at: str
    resolved_at: str | None
    affected: list[str]
    root_cause: str | None = Field(default=None, exclude_if=_omit_none)
    fix: str | None = Field(default=None, exclude_if=_omit_none)
    resolved_by: str | None = Field(default=None, exclude_if=_omit_none)
    source: str | None = Field(default=None, exclude_if=_omit_none)
    url: str | None = Field(default=None, exclude_if=_omit_none)


class SimilarIncident(BaseModel):
    incident: Incident
    similarity: float


class SuggestedEdge(BaseModel):
    model_config = {"populate_by_name": True}

    from_: str = Field(alias="from", serialization_alias="from")
    to: str
    type: str
    reason: str


class IncidentDetail(BaseModel):
    incident: Incident
    similar: list[SimilarIncident]
    suggested_edges: list[SuggestedEdge]


class NewIncident(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    symptom: str = Field(min_length=1, max_length=500)
    severity: Severity
    affected: list[Name] = Field(min_length=1, max_length=20)
    started_at: datetime | None = None


class EdgeRef(BaseModel):
    model_config = {"populate_by_name": True}

    from_: Name = Field(alias="from", serialization_alias="from")
    to: Name


class ResolveIncident(BaseModel):
    root_cause: Name
    fix: str = Field(min_length=1, max_length=1000)
    resolved_by: Name | None = None
    confirmed_edges: list[EdgeRef] = Field(default_factory=list, max_length=50)
    refuted_edges: list[EdgeRef] = Field(default_factory=list, max_length=50)


class GraphUpdates(BaseModel):
    created: int
    strengthened: int
    weakened: int


class ResolveResult(BaseModel):
    incident: Incident
    graph_updates: GraphUpdates


class ChangeCheckRequest(BaseModel):
    files: list[FilePath] = Field(default_factory=list, max_length=200)
    services: list[Name] = Field(default_factory=list, max_length=20)


class CoupledFile(BaseModel):
    path: str
    count: int


class ChangeCheck(BaseModel):
    services: list[GraphNode]
    impacted: list[ImpactItem]
    risk_score: int
    coupled_files: list[CoupledFile]
    reviewers: list[Responder]
    similar_incidents: list[SimilarIncident]


class Evidence(BaseModel):
    cypher: list[str]
    params: dict[str, object]
    returned_ids: list[str]
    note: str | None = Field(default=None, exclude_if=_omit_none)


class GraphPath(BaseModel):
    node_ids: list[str]
    edge_ids: list[str]
    paths: list[list[str]]


class AskContext(BaseModel):
    service: Name | None = None


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    context: AskContext | None = None


RepoStatus = Literal["queued", "cloning", "detecting", "ingesting", "ready", "failed"]


class ConnectRepo(BaseModel):
    url: str = Field(min_length=1, max_length=200)


class RepoOut(BaseModel):
    id: str
    owner: str
    name: str
    full_name: str
    url: str
    status: RepoStatus
    progress: int
    message: str | None
    error: str | None
    last_synced_at: str | None
    created_at: str
    is_demo: bool


EvaluationStatus = Literal["ok", "insufficient_history"]


class SystemScore(BaseModel):
    name: str
    predicted: int
    hits: int
    precision: float | None
    recall: float | None


class PairOut(BaseModel):
    a: str
    b: str


class Evaluation(BaseModel):
    status: EvaluationStatus
    reason: str | None
    commits_total: int
    commits_eligible: int
    train_commits: int
    test_commits: int
    split_at: str | None
    truth_pairs: int
    systems: list[SystemScore]
    hidden_hits: list[PairOut]
    created_at: str
