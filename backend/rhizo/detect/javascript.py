import json
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path

from rhizo.detect.files import language_of, read_text, rel, walk
from rhizo.detect.model import Detection, Edge, Service, service_name

SOURCE_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
_SPECIFIER = re.compile(
    r"""(?:\bimport\s[^'"`;]*?\bfrom\s*|\bexport\s[^'"`;]*?\bfrom\s*|\bimport\s*\(\s*|\brequire\s*\(\s*|\bimport\s+)"""
    r"""['"]([^'"\n]+)['"]"""
)


@dataclass(frozen=True)
class Unit:
    name: str
    package: str | None
    prefix: str


def _package_name(path: Path) -> str | None:
    try:
        data = json.loads(read_text(path) or "{}")
    except json.JSONDecodeError:
        return None
    name = data.get("name") if isinstance(data, dict) else None
    return name if isinstance(name, str) and name else None


def _units(root: Path) -> list[Unit]:
    found = []
    for path in walk(root, names=("package.json",)):
        package = _package_name(path)
        prefix = "" if path.parent == root else rel(root, path.parent) + "/"
        display = package or (path.parent.name if prefix else root.name)
        found.append(Unit(service_name(display), package, prefix))
    if len(found) > 1:
        found = [u for u in found if u.prefix]
    unique: dict[str, Unit] = {}
    for u in sorted(found, key=lambda u: len(u.prefix)):
        unique.setdefault(u.name, u)
    return list(unique.values())


def _bare_package(spec: str) -> str:
    parts = spec.split("/")
    return "/".join(parts[:2]) if spec.startswith("@") else parts[0]


def detect(root: Path) -> Detection:
    units = _units(root)
    out = Detection()
    if not units:
        return out
    for u in units:
        out.add_service(Service(u.name, u.prefix, language_of(root, u.prefix or None), {"js-imports"}))
    by_package = {u.package: u for u in units if u.package}
    by_prefix = sorted(units, key=lambda u: len(u.prefix), reverse=True)

    def owner(relpath: str) -> Unit | None:
        return next((u for u in by_prefix if relpath.startswith(u.prefix)), None)

    for path in walk(root, suffixes=SOURCE_SUFFIXES):
        relpath = rel(root, path)
        unit = owner(relpath)
        if unit is None:
            continue
        for spec in _SPECIFIER.findall(read_text(path) or ""):
            if spec.startswith("."):
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(relpath), spec))
                target = None if resolved.startswith("..") else owner(resolved)
            else:
                target = by_package.get(_bare_package(spec))
            if target and target is not unit:
                out.edges.append(
                    Edge("DEPENDS_ON", unit.name, target.name, "code", f"import {spec} in {relpath}")
                )
    return out
