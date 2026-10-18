import logging
import re
from typing import Annotated, TypeVar

import jwt
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from rhizo.config import settings
from rhizo.core.errors import BadRequest, NotFound, RhizoError, Unauthenticated
from rhizo.core.querylog import QueryScope
from rhizo.graph.client import GraphClient, repo_prefix
from rhizo.models import Basis, Envelope, Meta
from rhizo.repos import registry
from rhizo.repos.registry import Repo

T = TypeVar("T")

log = logging.getLogger("rhizo.auth")

TOKEN_ISSUER = "rhizo-web"
TOKEN_AUDIENCE = "rhizo-api"
_CLOCK_SKEW_S = 10
_USER_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_REPO_ID = re.compile(r"^[0-9a-f]{12}$")

_bearer = HTTPBearer(auto_error=False)


def current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> str:
    if not settings.auth_secret:
        raise RhizoError("AUTH_SECRET is not configured on the API")
    if credentials is None:
        raise Unauthenticated("missing bearer token")
    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.auth_secret,
            algorithms=["HS256"],
            audience=TOKEN_AUDIENCE,
            issuer=TOKEN_ISSUER,
            leeway=_CLOCK_SKEW_S,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as e:
        raise Unauthenticated("token expired") from e
    except jwt.InvalidTokenError as e:
        log.info("rejected bearer token: %s", type(e).__name__)
        raise Unauthenticated("invalid token") from e
    user_id = claims["sub"]
    if not isinstance(user_id, str) or not _USER_ID.fullmatch(user_id):
        raise Unauthenticated("invalid token")
    return user_id


User = Annotated[str, Depends(current_user)]


def current_repo(user: User, x_repo_id: Annotated[str | None, Header()] = None) -> Repo:
    if not x_repo_id:
        raise BadRequest("X-Repo-Id header is required: pick a connected repository")
    repo = registry.get(user, x_repo_id) if _REPO_ID.fullmatch(x_repo_id) else None
    if repo is None:
        raise NotFound("repository not found")
    return repo


def get_client(repo: Annotated[Repo, Depends(current_repo)]) -> GraphClient:
    return GraphClient(repo_prefix(repo.user_id, repo.id))


Client = Annotated[GraphClient, Depends(get_client)]


def envelope(data: T, qs: QueryScope, basis: Basis = "n/a") -> Envelope[T]:
    return Envelope[T](data=data, meta=Meta(basis=basis, took_ms=qs.took_ms, cypher=qs.cypher))


def optional_client(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    x_repo_id: Annotated[str | None, Header()] = None,
) -> GraphClient | None:
    if credentials is None or not x_repo_id:
        return None
    try:
        repo = current_repo(current_user(credentials), x_repo_id)
    except RhizoError:
        return None
    return GraphClient(repo_prefix(repo.user_id, repo.id))
