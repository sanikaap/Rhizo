from fastapi import APIRouter

from rhizo.api.deps import Client, envelope
from rhizo.core import querylog
from rhizo.core.validate import Name
from rhizo.models import Envelope, HiddenDependency
from rhizo.services.hidden import find_hidden

router = APIRouter(tags=["hidden"])


@router.get("/hidden-dependencies")
def hidden_dependencies(client: Client, service: Name | None = None) -> Envelope[list[HiddenDependency]]:
    with querylog.scope() as qs:
        data = find_hidden(client.topology(), service)
    return envelope(data, qs, "inferred" if data else "n/a")
