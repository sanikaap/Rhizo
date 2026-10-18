import logging
from pathlib import Path

from rhizo.detect import compose, javascript, k8s, python
from rhizo.detect.files import language_of
from rhizo.detect.model import Detection

log = logging.getLogger("rhizo.detect")

DETECTORS = (
    ("compose", compose.detect),
    ("kubernetes", k8s.detect),
    ("python", python.detect),
    ("javascript", javascript.detect),
)


def detect(root: Path) -> Detection:
    merged = Detection()
    for name, detector in DETECTORS:
        found = detector(root)
        log.info(
            "detect %s: %d services, %d resources, %d edges",
            name,
            len(found.services),
            len(found.resources),
            len(found.edges),
        )
        merged.merge(found)
    for svc in merged.services.values():
        if svc.language is None and svc.path_prefix is not None:
            svc.language = language_of(root, svc.path_prefix or None)
    return merged
