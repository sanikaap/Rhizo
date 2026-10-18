from fastapi import APIRouter

from rhizo.api.deps import Client, envelope
from rhizo.core import querylog
from rhizo.core.validate import check_name
from rhizo.models import Envelope, GraphNode, ServiceDetail
from rhizo.services import graphview

router = APIRouter(prefix="/services", tags=["services"])


@router.get("")
def list_services(client: Client) -> Envelope[list[GraphNode]]:
    with querylog.scope() as qs:
        data = graphview.services(client.topology())
    return envelope(data, qs)


@router.get("/{name}")
def get_service(name: str, client: Client) -> Envelope[ServiceDetail]:
    with querylog.scope() as qs:
        data = graphview.service_detail(client.topology(), client.memory(), check_name(name))
    return envelope(data, qs)
