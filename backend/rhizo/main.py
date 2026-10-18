import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rhizo.api.deps import current_user
from rhizo.api.routes import (
    agent,
    benchmark,
    graph,
    health,
    hidden,
    impact,
    incidents,
    rankings,
    repos,
    responders,
    services,
)
from rhizo.config import settings
from rhizo.core.errors import install_handlers
from rhizo.graph.client import close_all, ping
from rhizo.repos import jobs, registry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("rhizo")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    interrupted = registry.fail_interrupted()
    if interrupted:
        log.warning("%d sync(s) were interrupted by the last shutdown and are marked failed", interrupted)
    if ping():
        log.info("FalkorDB up at %s:%s", settings.falkordb_host, settings.falkordb_port)
    else:
        log.warning("FalkorDB unreachable at startup; analysis endpoints will return 503 until it is up")
    yield
    jobs.shutdown()
    close_all()


def create_app() -> FastAPI:
    app = FastAPI(title="Rhizo API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_handlers(app)
    app.include_router(health.router, prefix="/api")
    for module in (
        repos,
        impact,
        graph,
        services,
        hidden,
        rankings,
        incidents,
        responders,
        agent,
        benchmark,
    ):
        app.include_router(module.router, prefix="/api", dependencies=[Depends(current_user)])
    return app


app = create_app()
