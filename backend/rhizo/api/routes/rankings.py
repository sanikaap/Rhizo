from typing import Annotated

from fastapi import APIRouter, Query

from rhizo.api.deps import Client, envelope
from rhizo.core import querylog
from rhizo.core.validate import MAX_TOP_K
from rhizo.models import Envelope, RankingMetric, Rankings
from rhizo.services.rankings import rank

router = APIRouter(tags=["rankings"])


@router.get("/rankings")
def rankings(
    client: Client,
    metric: RankingMetric = "pagerank",
    top_k: Annotated[int, Query(ge=1, le=MAX_TOP_K)] = 10,
) -> Envelope[Rankings]:
    with querylog.scope() as qs:
        data = rank(client.topology(), metric, top_k)
    return envelope(data, qs)
