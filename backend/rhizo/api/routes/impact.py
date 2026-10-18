from fastapi import APIRouter

from rhizo.api.deps import Client, envelope
from rhizo.core import querylog
from rhizo.models import (
    BlastRadius,
    BlastRadiusRequest,
    ChangeCheck,
    ChangeCheckRequest,
    Envelope,
    UpstreamSuspects,
    UpstreamSuspectsRequest,
    WhatIf,
    WhatIfRequest,
)
from rhizo.services import changecheck, impact

router = APIRouter(prefix="/impact", tags=["impact"])


@router.post("/blast-radius")
def blast_radius(req: BlastRadiusRequest, client: Client) -> Envelope[BlastRadius]:
    with querylog.scope() as qs:
        result = impact.blast_radius(client.topology(), req)
    return envelope(result.data, qs, result.basis)


@router.post("/upstream-suspects")
def upstream_suspects(req: UpstreamSuspectsRequest, client: Client) -> Envelope[UpstreamSuspects]:
    with querylog.scope() as qs:
        result = impact.upstream_suspects(client.topology(), req)
    return envelope(result.data, qs, result.basis)


@router.post("/what-if")
def what_if(req: WhatIfRequest, client: Client) -> Envelope[WhatIf]:
    with querylog.scope() as qs:
        result = impact.what_if(client.topology(), req)
    return envelope(result.data, qs, result.basis)


@router.post("/change-check")
def change_check(req: ChangeCheckRequest, client: Client) -> Envelope[ChangeCheck]:
    with querylog.scope() as qs:
        result = changecheck.check(client.topology(), client.memory(), req)
    return envelope(result.data, qs, result.basis)
