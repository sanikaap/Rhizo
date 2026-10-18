import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path

from rhizo.detect.files import read_text, rel, walk
from rhizo.detect.model import Detection, Edge, Service, service_name

log = logging.getLogger("rhizo.detect.python")

PROJECT_FILES = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")
_NOT_A_SERVICE = frozenset(
    {"tests", "test", "docs", "doc", "examples", "example", "scripts", "benchmarks", "tools"}
)
_MAX_PROJECT_DEPTH = 3


@dataclass
class Unit:
    name: str
    prefix: str
    provides: set[str] = field(default_factory=set)


def _packages_in(directory: Path) -> list[Path]:
    return (
        sorted(
            d
            for d in directory.iterdir()
            if d.is_dir() and (d / "__init__.py").is_file() and d.name not in _NOT_A_SERVICE
        )
        if directory.is_dir()
        else []
    )


def _modules_in(directory: Path) -> set[str]:
    names = {p.name for p in _packages_in(directory)}
    names |= {p.stem for p in directory.glob("*.py") if p.stem not in {"__init__", "setup", "conftest"}}
    src = directory / "src"
    return names | (_modules_in(src) if src.is_dir() and src != directory else set())


def _units(root: Path) -> list[Unit]:
    project_dirs = sorted(
        {
            p.parent
            for p in walk(root, names=PROJECT_FILES)
            if p.parent != root and len(p.relative_to(root).parts) <= _MAX_PROJECT_DEPTH + 1
        }
    )
    project_dirs = [d for d in project_dirs if not _NOT_A_SERVICE & set(d.relative_to(root).parts)]
    outer = [d for d in project_dirs if not any(o != d and o in d.parents for o in project_dirs)]
    units = [Unit(service_name(d.name), rel(root, d) + "/", _modules_in(d)) for d in outer]
    packages = [
        p
        for base in (root, root / "src")
        for p in _packages_in(base)
        if not any(o == p or o in p.parents for o in outer)
    ]
    if not units and len(packages) == 1:
        pkg = packages[0]
        units = [
            Unit(service_name(f"{pkg.name}.{s.name}"), rel(root, s) + "/", {f"{pkg.name}.{s.name}"})
            for s in _packages_in(pkg)
        ]
        units.append(Unit(service_name(pkg.name), rel(root, pkg) + "/", {pkg.name}))
    else:
        units += [Unit(service_name(p.name), rel(root, p) + "/", {p.name}) for p in packages]
    return [u for u in units if u.provides]


def module_name(path: Path) -> str:
    parts = [] if path.name == "__init__.py" else [path.stem]
    d = path.parent
    while (d / "__init__.py").is_file():
        parts.insert(0, d.name)
        d = d.parent
    return ".".join(parts)


def _imports(tree: ast.AST, module: str, is_package: bool) -> list[str]:
    names = []
    package = module.split(".") if is_package else module.split(".")[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                base = node.module
            elif node.level > 0 and node.level - 1 <= len(package):
                up = package[: len(package) - (node.level - 1)]
                base = ".".join([*up, *([node.module] if node.module else [])])
            else:
                continue
            names += [f"{base}.{a.name}" for a in node.names if base]
    return names


def _resolve(module: str, index: dict[str, Unit]) -> Unit | None:
    parts = module.split(".")
    for i in range(len(parts), 0, -1):
        unit = index.get(".".join(parts[:i]))
        if unit:
            return unit
    return None


def detect(root: Path) -> Detection:
    units = _units(root)
    out = Detection()
    if not units:
        return out
    owners: dict[str, list[Unit]] = {}
    for u in units:
        out.add_service(Service(u.name, u.prefix, "python", {"python-imports"}))
        for name in u.provides:
            owners.setdefault(name, []).append(u)
    index = {name: us[0] for name, us in owners.items() if len(us) == 1}
    by_prefix = sorted(units, key=lambda u: len(u.prefix), reverse=True)

    for path in walk(root, suffixes=(".py",)):
        relpath = rel(root, path)
        unit = next((u for u in by_prefix if relpath.startswith(u.prefix)), None)
        if unit is None:
            continue
        try:
            tree = ast.parse(read_text(path) or "", filename=relpath)
        except (SyntaxError, ValueError):
            continue
        for module in _imports(tree, module_name(path), path.name == "__init__.py"):
            target = _resolve(module, index)
            if target and target is not unit:
                out.edges.append(
                    Edge("DEPENDS_ON", unit.name, target.name, "code", f"import {module} in {relpath}")
                )
    return out
