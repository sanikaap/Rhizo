from datetime import datetime
from typing import Annotated, get_args

from fastapi import APIRouter, Query

from rhizo.api.deps import Client, envelope
from rhizo.core import querylog
from rhizo.core.errors import BadRequest
from rhizo.core.validate import MAX_HOPS, MIN_HOPS, Name
from rhizo.models import Envelope, GraphData, Provenance
from rhizo.services import graphview

router = APIRouter(tags=["graph"])

_PROVENANCES: tuple[Provenance, ...] = get_args(Provenance)


def _parse_provenance(csv: str | None) -> list[Provenance] | None:
    if not csv:
        return None
    wanted = [p.strip() for p in csv.split(",") if p.strip()]
    unknown = [p for p in wanted if p not in _PROVENANCES]
    if unknown:
        raise BadRequest(f"unknown provenance {', '.join(unknown)}; expected {', '.join(_PROVENANCES)}")
    return [p for p in _PROVENANCES if p in wanted]


@router.get("/graph")
def get_graph(
    client: Client,
    center: Name | None = None,
    depth: Annotated[int, Query(ge=MIN_HOPS, le=MAX_HOPS)] = 2,
    min_confidence: Annotated[float, Query(ge=0.0, le=1.0)] = 0.0,
    provenance: str | None = None,
    as_of: datetime | None = None,
) -> Envelope[GraphData]:
    wanted = _parse_provenance(provenance)
    with querylog.scope() as qs:
        data = graphview.graph(client.topology(), center, depth, min_confidence, wanted, as_of)
    return envelope(data, qs)
