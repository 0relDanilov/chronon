"""Shapes the client expects, mirrored from vendor/ (see docs/contract.md)."""

import json
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, JsonValue

# Dataset types the state service never accepts from callers: the client
# unpickles `qmm_capabilities` and encrypts to the key in `key_qua`.
RESERVED_DATASET_TYPES = frozenset({"qmm_capabilities", "key_qua"})


class TaskStatus(StrEnum):
    """Task states, in the client's vocabulary (computers.py:430, 461)."""

    PENDING = "PENDING"
    RECEIVED = "RECEIVED"
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    REVOKED = "REVOKED"


TERMINAL = frozenset(
    {TaskStatus.SUCCESS, TaskStatus.FAILURE, TaskStatus.REVOKED}
)


class DatasetIn(BaseModel):
    """Body of ``POST /{backend}/state/`` (state.py:116-121)."""

    type: str = Field(min_length=1, max_length=60)
    data: JsonValue = None
    comment: str = Field(default="", max_length=300)
    parent_id: int | None = None


class DatasetMeta(BaseModel):
    """A dataset without its data (interfaces.py:34-49)."""

    id: int
    timestamp: datetime
    type: str
    comment: str
    producer: str
    parent_id: int | None


class Dataset(DatasetMeta):
    """A dataset with its backend and data (interfaces.py:27-31)."""

    backend: str
    data: JsonValue


class TimeSeriesPoint(BaseModel):
    """One point of ``GET /{backend}/timeseries/`` (interfaces.py:52-55)."""

    id: int
    t: datetime
    value: JsonValue


class TaskCreated(BaseModel):
    """Response of ``POST /task/{backend}/{workflow}``."""

    task_id: str


class TaskState(BaseModel):
    """Response of ``GET /task/{backend}/{id}``.

    ``task_result`` is always a JSON string encoding an object, because the
    client calls ``json.loads`` and then ``.get`` on it (computers.py:496-499).
    """

    task_status: TaskStatus
    task_result: str = "{}"


def result_json(
    result: dict[str, Any], stdout: str = "", stderr: str = ""
) -> str:
    """Encode a finished run the way the client reads it.

    Args:
        result: The workflow's result object.
        stdout: Captured standard output.
        stderr: Captured standard error; non-empty is shown as an error.

    Returns:
        A JSON string ``{"result": ..., "stdout": ..., "stderr": ...}``.
    """
    return json.dumps(
        {"result": result, "stdout": stdout, "stderr": stderr},
        default=encode_complex,
    )


def encode_complex(obj: object) -> object:
    """Encode complex numbers as the client decodes them (utilities.py:155).

    Args:
        obj: A value ``json`` couldn't serialize.

    Returns:
        ``{"__type__": "complex", "data": [re, im]}`` for complex numbers.

    Raises:
        TypeError: For any other type.
    """
    if isinstance(obj, complex):
        return {"__type__": "complex", "data": [obj.real, obj.imag]}
    raise TypeError(f"{type(obj).__name__} is not JSON serializable")
