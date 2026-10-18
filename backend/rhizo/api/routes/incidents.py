from fastapi import APIRouter

from rhizo.api.deps import Client, envelope
from rhizo.core import querylog
from rhizo.core.validate import check_name
from rhizo.models import Envelope, Incident, IncidentDetail, NewIncident, ResolveIncident, ResolveResult
from rhizo.services import incidents

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("")
def list_incidents(client: Client) -> Envelope[list[Incident]]:
    with querylog.scope() as qs:
        data = incidents.list_incidents(client.memory())
    return envelope(data, qs)


@router.post("")
def create_incident(body: NewIncident, client: Client) -> Envelope[Incident]:
    with querylog.scope() as qs:
        data = incidents.create(client.topology(), client.memory(), body)
    return envelope(data, qs)


@router.get("/{incident_id}")
def get_incident(incident_id: str, client: Client) -> Envelope[IncidentDetail]:
    with querylog.scope() as qs:
        data = incidents.detail(client.topology(), client.memory(), check_name(incident_id))
    return envelope(data, qs, "inferred" if data.suggested_edges else "n/a")


@router.post("/{incident_id}/resolve")
def resolve_incident(incident_id: str, body: ResolveIncident, client: Client) -> Envelope[ResolveResult]:
    with querylog.scope() as qs:
        data = incidents.resolve(client.topology(), client.memory(), check_name(incident_id), body)
    return envelope(data, qs)
