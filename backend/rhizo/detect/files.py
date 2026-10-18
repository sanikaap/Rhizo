import os
from collections.abc import Iterator
from pathlib import Path

IGNORED_DIRS = frozenset(
    {
        ".git", "node_modules", "vendor", "third_party", "dist", "build", "out", "target", ".next", ".nuxt",
        "coverage", "__pycache__", ".venv", "venv", "env", ".tox", "site-packages", "bower_components",
    }
)  # fmt: skip
MAX_FILE_BYTES = 1_000_000
MAX_FILES = 50_000


def walk(
    root: Path, suffixes: tuple[str, ...] | None = None, names: tuple[str, ...] | None = None
) -> Iterator[Path]:
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            if suffixes and not name.endswith(suffixes):
                continue
            if names and name not in names:
                continue
            path = Path(dirpath, name)
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                continue
            seen += 1
            if seen > MAX_FILES:
                return
            yield path


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def prefix_of(root: Path, directory: Path) -> str | None:
    try:
        r = directory.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None
    return None if r in ("", ".") else f"{r}/"


_LANGUAGES = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".go": "go", ".java": "java", ".kt": "kotlin", ".cs": "csharp",
    ".rb": "ruby", ".rs": "rust", ".php": "php", ".scala": "scala", ".ex": "elixir",
}  # fmt: skip


def language_of(root: Path, prefix: str | None, limit: int = 2000) -> str | None:
    counts: dict[str, int] = {}
    for i, path in enumerate(walk(root / prefix if prefix else root, suffixes=tuple(_LANGUAGES))):
        if i >= limit:
            break
        lang = _LANGUAGES[path.suffix]
        counts[lang] = counts.get(lang, 0) + 1
    return max(counts, key=lambda k: counts[k]) if counts else None
