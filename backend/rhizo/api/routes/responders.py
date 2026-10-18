from typing import Annotated

from fastapi import APIRouter, Query

from rhizo.api.deps import Client, envelope
from rhizo.core import querylog
from rhizo.core.validate import Name
from rhizo.models import Envelope, Responder
from rhizo.services.responders import recommend

router = APIRouter(tags=["responders"])


@router.get("/responders")
def responders(
    client: Client, service: Annotated[list[Name], Query(min_length=1, max_length=20)]
) -> Envelope[list[Responder]]:
    with querylog.scope() as qs:
        data = recommend(client.topology(), client.memory(), sorted(set(service)))
    return envelope(data, qs)
