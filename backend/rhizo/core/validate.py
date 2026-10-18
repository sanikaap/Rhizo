import re
from typing import Annotated

from pydantic import AfterValidator

from rhizo.core.errors import BadRequest

NAME_PATTERN = r"^[A-Za-z0-9._-]{1,64}$"
_NAME_RE = re.compile(NAME_PATTERN)

MIN_HOPS, MAX_HOPS = 1, 6
MAX_TOP_K = 50


def check_name(value: str) -> str:
    if not _NAME_RE.fullmatch(value):
        raise BadRequest(f"invalid name {value!r}: must match {NAME_PATTERN}")
    return value


def check_hops(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not MIN_HOPS <= value <= MAX_HOPS:
        raise BadRequest(f"max_hops must be an integer in {MIN_HOPS}..{MAX_HOPS}")
    return value


def _name_field(value: str) -> str:
    if not _NAME_RE.fullmatch(value):
        raise ValueError(f"must match {NAME_PATTERN}")
    return value


Name = Annotated[str, AfterValidator(_name_field)]


_PATH_RE = re.compile(r"^(?!/)(?!.*\.\.)[A-Za-z0-9._/@+-]{1,256}$")


def _path_field(value: str) -> str:
    if not _PATH_RE.fullmatch(value):
        raise ValueError("must be a repo-relative path without '..'")
    return value


FilePath = Annotated[str, AfterValidator(_path_field)]
