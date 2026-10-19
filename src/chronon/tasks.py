"""Task status: hot copy in Valkey, durable record in Postgres.

Polls read only Valkey (``HGETALL task:{id}``). Postgres is written on every
state change and read only when the hot copy is missing (expired or lost).
"""

import json
from datetime import UTC, datetime
from functools import cache
from typing import Any, cast

import redis
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from chronon.contract import TaskStatus
from chronon.db import TaskRow, get_engine
from chronon.settings import get_settings


@cache
def get_valkey() -> "redis.Redis":
    """Return the process-wide Valkey client (strings, not bytes).

    Returns:
        A redis-py client.
    """
    return redis.Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
        get_settings().valkey_url, decode_responses=True
    )


def task_key(task_id: str) -> str:
    """Return the Valkey key of a task's hot status.

    Args:
        task_id: The task.

    Returns:
        ``task:{id}``.
    """
    return f"task:{task_id}"


def _now() -> datetime:
    return datetime.now(UTC)


def new_task(
    task_id: str,
    backend: str,
    workflow: str,
    user_id: str,
    payload: Any,
    status: TaskStatus = TaskStatus.PENDING,
    result: str = "{}",
) -> dict[str, str]:
    """Write a task's durable row and return its hot-hash fields.

    The caller writes the fields to Valkey: directly (``create``), or inside
    the queue's atomic push (``chronon.queue.submit``).

    Args:
        task_id: A new UUID.
        backend: Backend name.
        workflow: Workflow name.
        user_id: The submitting user.
        payload: The validated payload.
        status: Initial status.
        result: Initial ``task_result`` JSON string.

    Returns:
        Field/value pairs for ``task:{id}``.
    """
    now = _now()
    finished = (
        now if status in (TaskStatus.SUCCESS, TaskStatus.FAILURE) else None
    )
    with Session(get_engine()) as s, s.begin():
        s.add(
            TaskRow(
                id=task_id,
                backend=backend,
                workflow=workflow,
                user_id=user_id,
                payload=payload,
                status=status.value,
                result=result,
                submitted_at=now,
                started_at=finished,
                finished_at=finished,
            )
        )
    fields = {
        "status": status.value,
        "result": result,
        "user": user_id,
        "backend": backend,
        "workflow": workflow,
        "payload": json.dumps(payload),
        "submitted_at": f"{now.timestamp():.6f}",
    }
    if finished is not None:
        fields["started_at"] = fields["finished_at"] = fields["submitted_at"]
    return fields


def create(
    task_id: str,
    backend: str,
    workflow: str,
    user_id: str,
    payload: Any,
    status: TaskStatus = TaskStatus.PENDING,
    result: str = "{}",
) -> None:
    """Record a task that isn't queued (inline workflows) in both stores.

    Args:
        task_id: A new UUID.
        backend: Backend name.
        workflow: Workflow name.
        user_id: The submitting user.
        payload: The validated payload.
        status: Initial status.
        result: Initial ``task_result`` JSON string.
    """
    fields: dict[Any, Any] = new_task(
        task_id, backend, workflow, user_id, payload, status, result
    )
    pipe = get_valkey().pipeline()  # pyright: ignore[reportUnknownMemberType]
    pipe.hset(task_key(task_id), mapping=fields)
    pipe.expire(task_key(task_id), get_settings().task_ttl_seconds)
    pipe.execute()


def delete_durable(task_id: str) -> None:
    """Remove a task's row (used when the queue refuses it).

    Args:
        task_id: The task.
    """
    with Session(get_engine()) as s, s.begin():
        s.execute(delete(TaskRow).where(TaskRow.id == task_id))


def hot(task_id: str) -> dict[str, str]:
    """Read a task's hot status from Valkey only.

    Args:
        task_id: The task.

    Returns:
        The hash fields; empty if the key is missing.
    """
    return cast(dict[str, str], get_valkey().hgetall(task_key(task_id)))


def durable(task_id: str) -> TaskRow | None:
    """Read a task from Postgres (the fallback path).

    Args:
        task_id: The task.

    Returns:
        The row, or None.
    """
    with Session(get_engine()) as s:
        return s.get(TaskRow, task_id)


def set_status(
    task_id: str, status: TaskStatus, result: str | None = None
) -> None:
    """Move a task to a new status in both stores.

    Args:
        task_id: The task.
        status: The new status.
        result: A new ``task_result`` JSON string, if any.
    """
    now = _now()
    values: dict[str, Any] = {"status": status.value}
    hot_fields: dict[Any, Any] = {"status": status.value}
    if status is TaskStatus.STARTED:
        values["started_at"] = now
        hot_fields["started_at"] = f"{now.timestamp():.6f}"
    if status in (TaskStatus.SUCCESS, TaskStatus.FAILURE, TaskStatus.REVOKED):
        values["finished_at"] = now
        hot_fields["finished_at"] = f"{now.timestamp():.6f}"
    if result is not None:
        values["result"] = result
        hot_fields["result"] = result
    with Session(get_engine()) as s, s.begin():
        s.execute(update(TaskRow).where(TaskRow.id == task_id).values(**values))
    get_valkey().hset(task_key(task_id), mapping=hot_fields)
