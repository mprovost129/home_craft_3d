# core/logging_context.py
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Optional

_local = threading.local()


@dataclass
class RequestContext:
    request_id: str
    user_id: Optional[int] = None
    path: str = ""


def set_context(*, request_id: str, user_id: Optional[int], path: str) -> None:
    _local.ctx = RequestContext(request_id=request_id, user_id=user_id, path=path)


def clear_context() -> None:
    if hasattr(_local, "ctx"):
        delattr(_local, "ctx")


def get_context() -> RequestContext | None:
    return getattr(_local, "ctx", None)


def new_request_id() -> str:
    return uuid.uuid4().hex
