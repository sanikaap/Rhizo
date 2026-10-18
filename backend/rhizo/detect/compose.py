import logging
import re
from pathlib import Path
from typing import Any

import yaml

from rhizo.detect.files import prefix_of, read_text, rel, walk
from rhizo.detect.model import Detection, Edge, Resource, Service, service_name
from rhizo.detect.refs import env_evidence, host_reference, resource_kind

log = logging.getLogger("rhizo.detect.compose")

COMPOSE_FILE = re.compile(r"^(docker-)?compose(\.[\w-]+)?\.ya?ml$")


def is_compose_file(path: Path) -> bool:
    return bool(COMPOSE_FILE.fullmatch(path.name))


def _env_items(env: Any) -> list[tuple[str, str]]:
    if isinstance(env, dict):
        return [(str(k), str(v)) for k, v in env.items() if v is not None]
    if isinstance(env, list):
        return [tuple(str(item).split("=", 1)) for item in env if "=" in str(item)]  # type: ignore[misc]
    return []


def _depends_on(spec: dict[str, Any]) -> list[str]:
    deps = spec.get("depends_on") or []
    names = list(deps) if isinstance(deps, dict | list) else []
    links = [str(link).split(":")[0] for link in spec.get("links") or [] if isinstance(link, str)]
    return [str(n) for n in names + links]


def _build_dir(compose_path: Path, spec: dict[str, Any]) -> Path | None:
    build = spec.get("build")
    context = build.get("context", ".") if isinstance(build, dict) else build
    return (compose_path.parent / context) if isinstance(context, str) else None


def _parse(root: Path, path: Path, out: Detection) -> None:
    text = read_text(path)
    try:
        doc = yaml.safe_load(text or "")
    except yaml.YAMLError as e:
        log.info("compose: %s is not valid YAML (%s); skipped", rel(root, path), type(e).__name__)
        return
    services = doc.get("services") if isinstance(doc, dict) else None
    if not isinstance(services, dict):
        return
    relpath = rel(root, path)
    names = {raw: service_name(str(raw)) for raw in services}
    by_host = {str(raw).lower(): name for raw, name in names.items()}
    for raw, spec in services.items():
        spec = spec if isinstance(spec, dict) else {}
        name = names[raw]
        build_dir = _build_dir(path, spec)
        kind = None if build_dir else resource_kind(spec.get("image"))
        if kind:
            out.resources[name] = Resource(name, kind)
        else:
            out.add_service(
                Service(name, prefix_of(root, build_dir) if build_dir else None, detected_by={"compose"})
            )
        for dep in _depends_on(spec):
            target = names.get(dep) or by_host.get(dep.lower())
            if target:
                out.edges.append(
                    Edge("DEPENDS_ON", name, target, "declared", f"depends_on {dep} in {relpath}")
                )
        for key, value in _env_items(spec.get("environment")):
            ref = host_reference(value)
            target = by_host.get(ref[0]) if ref else None
            if ref and target and target != name:
                out.edges.append(
                    Edge("DEPENDS_ON", name, target, "declared", env_evidence(key, *ref, relpath))
                )


def detect(root: Path) -> Detection:
    out = Detection()
    for path in walk(root, suffixes=(".yml", ".yaml")):
        if is_compose_file(path):
            _parse(root, path, out)
    return out
