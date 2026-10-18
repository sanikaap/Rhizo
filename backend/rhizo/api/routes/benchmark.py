from typing import Annotated

from fastapi import APIRouter, Depends

from rhizo.api.deps import User, current_repo, envelope
from rhizo.core import querylog
from rhizo.core.errors import NotFound
from rhizo.models import Envelope, Evaluation
from rhizo.repos import registry
from rhizo.repos.registry import Repo

router = APIRouter(prefix="/benchmark", tags=["benchmark"])


@router.get("/results")
def results(user: User, repo: Annotated[Repo, Depends(current_repo)]) -> Envelope[Evaluation]:
    stored = registry.evaluation(user, repo.id)
    if stored is None:
        raise NotFound("no evaluation yet: sync this repository first")
    return envelope(Evaluation.model_validate_json(stored), querylog.QueryScope())
