import re

_HOST_PORT = re.compile(r"^(?P<host>[A-Za-z0-9][A-Za-z0-9.-]*):(?P<port>\d{1,5})$")
_URL = re.compile(
    r"^[A-Za-z][A-Za-z0-9+.-]*://(?:[^@/\s]*@)?(?P<host>[A-Za-z0-9][A-Za-z0-9.-]*)(?::(?P<port>\d{1,5}))?(?:[/?#].*)?$"
)
_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*$")

_RESOURCE_IMAGES: tuple[tuple[str, str], ...] = (
    ("redis", "cache"), ("memcached", "cache"), ("valkey", "cache"),
    ("postgres", "database"), ("mysql", "database"), ("mariadb", "database"), ("mongo", "database"),
    ("cassandra", "database"), ("elasticsearch", "database"), ("opensearch", "database"),
    ("kafka", "queue"), ("rabbitmq", "queue"), ("nats", "queue"), ("zookeeper", "config"),
    ("vault", "secret"), ("consul", "config"),
)  # fmt: skip


def resource_kind(image: object) -> str | None:
    if not isinstance(image, str):
        return None
    repo = image.split("@")[0].rsplit("/", 1)[-1].split(":")[0].lower()
    return next((kind for needle, kind in _RESOURCE_IMAGES if needle in repo), None)


def host_reference(value: object) -> tuple[str, str | None] | None:
    if not isinstance(value, str):
        return None
    v = value.strip()
    m = _HOST_PORT.fullmatch(v) or _URL.fullmatch(v)
    if m:
        return m["host"].split(".")[0].lower(), m["port"]
    if _HOST.fullmatch(v):
        return v.split(".")[0].lower(), None
    return None


def env_evidence(key: str, host: str, port: str | None, relpath: str) -> str:
    return f"env {key}={host}{':' + port if port else ''} in {relpath}"
