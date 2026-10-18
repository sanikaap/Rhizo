import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from rhizo.detect.compose import is_compose_file
from rhizo.detect.files import read_text, rel, walk
from rhizo.detect.model import Detection, Edge, Resource, Service, service_name
from rhizo.detect.refs import env_evidence, host_reference, resource_kind

log = logging.getLogger("rhizo.detect.k8s")

WORKLOAD_KINDS = frozenset({"Deployment", "StatefulSet", "DaemonSet"})


@dataclass(frozen=True)
class Workload:
    name: str
    relpath: str
    resource_kind: str | None
    labels: dict[str, str]
    env: list[tuple[str, str]]


def _documents(root: Path) -> list[tuple[str, dict[str, Any]]]:
    docs = []
    for path in walk(root, suffixes=(".yml", ".yaml")):
        if is_compose_file(path) or ".github" in path.parts:
            continue
        text = read_text(path) or ""
        if "apiVersion" not in text or "kind" not in text:
            continue
        try:
            docs += [
                (rel(root, path), d) for d in yaml.safe_load_all(text) if isinstance(d, dict) and "kind" in d
            ]
        except yaml.YAMLError:
            log.debug("k8s: %s is not plain YAML (template?); skipped", rel(root, path))
    return docs


def _workload(relpath: str, doc: dict[str, Any]) -> Workload | None:
    raw = (doc.get("metadata") or {}).get("name")
    if not isinstance(raw, str):
        return None
    pod = (doc.get("spec") or {}).get("template") or {}
    pod_spec = pod.get("spec") or {}
    containers = [*(pod_spec.get("initContainers") or []), *(pod_spec.get("containers") or [])]
    env = [
        (str(e["name"]), str(e["value"]))
        for c in containers
        if isinstance(c, dict)
        for e in c.get("env") or []
        if isinstance(e, dict) and "name" in e and "value" in e
    ]
    images = [c.get("image") for c in containers if isinstance(c, dict)]
    kind = next((k for k in map(resource_kind, images) if k), None)
    labels = (pod.get("metadata") or {}).get("labels") or {}
    return Workload(service_name(raw), relpath, kind, {str(k): str(v) for k, v in labels.items()}, env)


def detect(root: Path) -> Detection:
    workloads: dict[str, Workload] = {}
    selectors: dict[str, dict[str, str]] = {}
    for relpath, doc in _documents(root):
        if doc["kind"] in WORKLOAD_KINDS and (w := _workload(relpath, doc)):
            workloads.setdefault(w.name, w)
        elif doc["kind"] == "Service" and isinstance((doc.get("metadata") or {}).get("name"), str):
            selector = (doc.get("spec") or {}).get("selector") or {}
            selectors[doc["metadata"]["name"].lower()] = {str(k): str(v) for k, v in selector.items()}

    aliases = {w.name.lower(): w.name for w in workloads.values()}
    for svc, selector in selectors.items():
        picked = [w.name for w in workloads.values() if selector and selector.items() <= w.labels.items()]
        if len(picked) == 1:
            aliases.setdefault(svc, picked[0])

    out = Detection()
    for w in workloads.values():
        if w.resource_kind:
            out.resources[w.name] = Resource(w.name, w.resource_kind)
            continue
        prefix = next((p for p in (f"src/{w.name}/", f"{w.name}/") if (root / p).is_dir()), None)
        out.add_service(Service(w.name, prefix, detected_by={"kubernetes"}))
    for w in workloads.values():
        if w.resource_kind:
            continue
        for key, value in w.env:
            ref = host_reference(value)
            target = aliases.get(ref[0]) if ref and ref[1] else None
            if ref and target and target != w.name:
                out.edges.append(
                    Edge("DEPENDS_ON", w.name, target, "declared", env_evidence(key, *ref, w.relpath))
                )
            elif ref and ref[1] and not target:
                log.info("k8s: %s %s points at unknown host %r; ignored", w.relpath, key, ref[0])
    return out
