from typing import Annotated

from fastapi import APIRouter, Depends

from rhizo.api.deps import envelope, optional_client
from rhizo.core import querylog
from rhizo.core.errors import UpstreamError
from rhizo.graph.client import GraphClient, ping
from rhizo.models import Envelope, GraphCounts, Health
from rhizo.services.graphview import graph_counts

router = APIRouter(tags=["health"])


@router.get("/health")
def health(client: Annotated[GraphClient | None, Depends(optional_client)]) -> Envelope[Health]:
    with querylog.scope() as qs:
        if not ping():
            raise UpstreamError("FalkorDB unreachable")
        counts = (
            graph_counts(client.topology(), client.memory())
            if client
            else GraphCounts(services=0, edges=0, incidents=0)
        )
    return envelope(Health(falkordb="up", graph_counts=counts), qs)
