import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from rhizo.config import settings
from rhizo.core.errors import RhizoError

_SAFE_CONFIG = [
    "-c", "core.hooksPath=/dev/null",
    "-c", "core.fsmonitor=false",
    "-c", "core.symlinks=false",
    "-c", "protocol.allow=never",
    "-c", "protocol.https.allow=always",
    "-c", "submodule.recurse=false",
    "-c", "credential.helper=",
]  # fmt: skip


class GitError(RhizoError):
    pass


CLONE_ATTEMPTS = 2


def _env(home: Path) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/bin/false",
        "GIT_LFS_SKIP_SMUDGE": "1",
        "LANG": "C",
    }


def run_git(args: list[str], cwd: Path) -> str:
    try:
        out = subprocess.run(
            ["git", *_SAFE_CONFIG, "-c", f"safe.directory={cwd}", *args],
            cwd=cwd,
            env=_env(cwd),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=settings.git_timeout_s,
            check=True,
        )
    except subprocess.TimeoutExpired as e:
        raise GitError(f"git {args[0]} timed out after {settings.git_timeout_s}s") from e
    except subprocess.CalledProcessError as e:
        raise GitError(
            f"git {args[0]} failed: {e.stderr.strip().splitlines()[-1] if e.stderr.strip() else e.returncode}"
        ) from e
    except OSError as e:
        raise GitError(f"git is not available: {e}") from e
    return out.stdout


def _tree_size(root: Path) -> int:
    total = 0
    for dirpath, _, files in os.walk(root, followlinks=False):
        for f in files:
            p = Path(dirpath, f)
            if not p.is_symlink():
                total += p.stat().st_size
    return total


@contextmanager
def clone(clone_url: str) -> Iterator[Path]:
    workdir = Path(tempfile.mkdtemp(prefix="rhizo-clone-"))
    try:
        dest = workdir / "repo"
        args = [
            "clone",
            "--filter=blob:none",
            f"--depth={settings.git_max_commits}",
            "--single-branch",
            "--no-tags",
            "--",
            clone_url,
            str(dest),
        ]
        for attempt in range(1, CLONE_ATTEMPTS + 1):
            try:
                run_git(args, cwd=workdir)
                break
            except GitError:
                shutil.rmtree(dest, ignore_errors=True)
                if attempt == CLONE_ATTEMPTS:
                    raise
        size = _tree_size(dest)
        if size > settings.max_repo_size_mb * 1024 * 1024:
            raise GitError(
                f"checkout is {size // (1024 * 1024)} MB; the limit is {settings.max_repo_size_mb} MB"
            )
        yield dest
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
