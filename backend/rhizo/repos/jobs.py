import logging
from concurrent.futures import ThreadPoolExecutor

from rhizo.config import settings
from rhizo.core.errors import RhizoError
from rhizo.repos import pipeline, registry

log = logging.getLogger("rhizo.jobs")

_executor: ThreadPoolExecutor | None = None


def _pool() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=settings.sync_workers, thread_name_prefix="rhizo-sync")
    return _executor


def run_sync(repo_id: str) -> None:
    try:
        pipeline.sync(repo_id)
    except RhizoError as e:
        log.warning("sync %s failed: %s", repo_id, e.message)
        registry.update(repo_id, status="failed", progress=100, error=e.message)
    except Exception:
        log.exception("sync %s crashed", repo_id)
        registry.update(
            repo_id, status="failed", progress=100, error="Sync failed unexpectedly. See the server log."
        )


def enqueue(repo_id: str) -> None:
    _pool().submit(run_sync, repo_id)


def shutdown() -> None:
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
