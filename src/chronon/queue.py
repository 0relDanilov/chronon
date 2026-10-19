"""Valkey-backed device queue with fifo and per-user fair (round-robin) modes.

Keys for backend ``b``:

- ``sched:{b}``: the mode, ``fifo`` or ``fair`` (missing means ``fair``).
- ``q:{b}:fifo``: one global list (fifo mode).
- ``q:{b}:user:{u}``: one list per user, and ``q:{b}:rot`` (a list) plus
  ``q:{b}:rotset`` (a set) of users with queued work, in turn order (fair mode).
- ``q:{b}:processing``: tasks popped but not finished (the reliable-queue
  pattern: a crashed worker's task is re-queued on startup).
- ``occupancy:{b}``: a stream of who held the device, and when.

Push and pop are Lua scripts, so each is atomic in Valkey: the cap check, the
enqueue, the rotation and the task's hot hash happen in one step. The scripts
build per-user key names at run time, which is fine on one Valkey instance
and would need hash tags on Valkey Cluster (ADR-0005).
"""

import json
from typing import Any, Literal, cast

from chronon import tasks
from chronon.contract import TaskStatus
from chronon.settings import get_settings

Mode = Literal["fifo", "fair"]
USER_CAP = 5  # queued runs per user, fair mode only

_PUSH = """
-- KEYS: sched, fifo, user queue, rot, rotset, task hash
-- ARGV: task_id, user, cap, ttl, then field/value pairs for the task hash
local mode = redis.call('GET', KEYS[1]) or 'fair'
if mode ~= 'fifo' then
  local queued = redis.call('LLEN', KEYS[3])
  if queued >= tonumber(ARGV[3]) then
    return {'capped', queued}
  end
end
redis.call('HSET', KEYS[6], unpack(ARGV, 5))
redis.call('EXPIRE', KEYS[6], tonumber(ARGV[4]))
if mode == 'fifo' then
  redis.call('RPUSH', KEYS[2], ARGV[1])
  return {mode, redis.call('LLEN', KEYS[2])}
end
redis.call('RPUSH', KEYS[3], ARGV[1])
if redis.call('SADD', KEYS[5], ARGV[2]) == 1 then
  redis.call('RPUSH', KEYS[4], ARGV[2])
end
return {mode, redis.call('LLEN', KEYS[3])}
"""

_POP = """
-- KEYS: sched, fifo, rot, rotset, processing; ARGV: user-queue key prefix
local mode = redis.call('GET', KEYS[1]) or 'fair'
local function pop_fair()
  local n = redis.call('LLEN', KEYS[3])
  for _ = 1, n do
    local user = redis.call('LPOP', KEYS[3])
    if not user then return false end
    local uq = ARGV[1] .. user
    local task = redis.call('LPOP', uq)
    if redis.call('LLEN', uq) > 0 then
      redis.call('RPUSH', KEYS[3], user)   -- back of the line
    else
      redis.call('SREM', KEYS[4], user)
    end
    if task then return task end
  end
  return false
end
local task
-- Drain the other mode's structure too, so a switch strands nothing.
if mode == 'fifo' then
  task = redis.call('LPOP', KEYS[2]) or pop_fair()
else
  task = pop_fair() or redis.call('LPOP', KEYS[2])
end
if task then redis.call('RPUSH', KEYS[5], task) end
return task
"""


class QueueFull(Exception):
    """The user already has ``USER_CAP`` runs queued (fair mode)."""

    def __init__(self, backend: str, queued: int) -> None:
        super().__init__(
            f"You already have {queued} runs queued on {backend}, the "
            f"per-user limit in fair mode. They run in turn with other "
            f"users; submit more when one finishes."
        )


def _k(backend: str) -> dict[str, str]:
    return {
        "sched": f"sched:{backend}",
        "fifo": f"q:{backend}:fifo",
        "user": f"q:{backend}:user:",
        "rot": f"q:{backend}:rot",
        "rotset": f"q:{backend}:rotset",
        "processing": f"q:{backend}:processing",
        "occupancy": f"occupancy:{backend}",
    }


def mode(backend: str) -> Mode:
    """Return the scheduling mode.

    Args:
        backend: Backend name.

    Returns:
        ``fifo`` or ``fair`` (the default).
    """
    raw = cast(str | None, tasks.get_valkey().get(_k(backend)["sched"]))
    return "fifo" if raw == "fifo" else "fair"


def set_mode(backend: str, new: Mode) -> None:
    """Switch the scheduling mode; queued work is kept (pop drains both).

    Args:
        backend: Backend name.
        new: The mode.
    """
    tasks.get_valkey().set(_k(backend)["sched"], new)


def submit(
    task_id: str,
    backend: str,
    workflow: str,
    user_id: str,
    payload: Any,
    cap: int = USER_CAP,
) -> int:
    """Record a device task and queue it, atomically in Valkey.

    The durable row is written first; if the queue refuses the task (cap),
    the row is removed again.

    Args:
        task_id: A new UUID.
        backend: Backend name.
        workflow: Workflow name.
        user_id: The submitting user.
        payload: The validated payload.
        cap: Per-user queue cap in fair mode.

    Returns:
        The queue length the task joined (global in fifo, the user's in fair).

    Raises:
        QueueFull: In fair mode, if the user already has ``cap`` queued.
    """
    k = _k(backend)
    fields = tasks.new_task(task_id, backend, workflow, user_id, payload)
    flat: list[str] = [x for kv in fields.items() for x in kv]
    v = tasks.get_valkey()
    res = cast(
        list[Any],
        v.eval(  # pyright: ignore[reportUnknownMemberType]
            _PUSH,
            6,
            k["sched"],
            k["fifo"],
            k["user"] + user_id,
            k["rot"],
            k["rotset"],
            tasks.task_key(task_id),
            task_id,
            user_id,
            str(cap),
            str(get_settings().task_ttl_seconds),
            *flat,
        ),
    )
    if res[0] == "capped":
        tasks.delete_durable(task_id)
        raise QueueFull(backend, int(res[1]))
    return int(res[1])


def pop(backend: str) -> str | None:
    """Take the next task for the device and mark it as processing.

    Args:
        backend: Backend name.

    Returns:
        A task id, or None if nothing is queued.
    """
    k = _k(backend)
    got = tasks.get_valkey().eval(  # pyright: ignore[reportUnknownMemberType]
        _POP,
        5,
        k["sched"],
        k["fifo"],
        k["rot"],
        k["rotset"],
        k["processing"],
        k["user"],
    )
    return cast(str | None, got)


def done(backend: str, task_id: str) -> None:
    """Remove a finished task from the processing list.

    Args:
        backend: Backend name.
        task_id: The task.
    """
    tasks.get_valkey().lrem(_k(backend)["processing"], 0, task_id)


def requeue_processing(backend: str) -> list[str]:
    """Put tasks a previous worker left half-done back at the front.

    Called once at worker startup (one worker per device, so no race).

    Args:
        backend: Backend name.

    Returns:
        The task ids re-queued.
    """
    k = _k(backend)
    v = tasks.get_valkey()
    stranded = cast(list[str], v.lrange(k["processing"], 0, -1))
    for task_id in reversed(stranded):
        hot = tasks.hot(task_id)
        user = hot.get("user")
        if not user or hot.get("status") in ("SUCCESS", "FAILURE", "REVOKED"):
            continue
        tasks.set_status(task_id, TaskStatus.PENDING)
        if mode(backend) == "fifo":
            v.lpush(k["fifo"], task_id)
        else:
            v.lpush(k["user"] + user, task_id)
            if v.sadd(k["rotset"], user) == 1:
                v.lpush(k["rot"], user)
    v.delete(k["processing"])
    return stranded


def revoke(backend: str, task_id: str) -> TaskStatus:
    """Revoke a task: dequeue it if pending, flag it if running.

    Args:
        backend: Backend name.
        task_id: The task.

    Returns:
        ``REVOKED`` if it was still queued; ``STARTED`` if it's running (the
        worker checks the flag before the run phase).
    """
    k = _k(backend)
    v = tasks.get_valkey()
    user = tasks.hot(task_id).get("user", "")
    removed = v.lrem(k["fifo"], 0, task_id) + v.lrem(
        k["user"] + user, 0, task_id
    )
    if removed:
        tasks.set_status(task_id, TaskStatus.REVOKED)
        return TaskStatus.REVOKED
    v.set(f"revoke:{task_id}", "1", ex=3600)
    return TaskStatus.STARTED


def revoke_requested(task_id: str) -> bool:
    """Whether someone asked to revoke a running task.

    Args:
        task_id: The task.

    Returns:
        True if the flag is set.
    """
    return bool(tasks.get_valkey().exists(f"revoke:{task_id}"))


def record_occupancy(
    backend: str,
    user: str,
    task_id: str,
    workflow: str,
    start: float,
    end: float,
) -> None:
    """Append who held the device, and when, to the occupancy stream.

    Args:
        backend: Backend name.
        user: Who ran.
        task_id: The task.
        workflow: The workflow.
        start: Device acquired (Unix seconds).
        end: Device released (Unix seconds).
    """
    entry: dict[Any, Any] = {
        "user": user,
        "task": task_id,
        "workflow": workflow,
        "start": f"{start:.6f}",
        "end": f"{end:.6f}",
    }
    tasks.get_valkey().xadd(  # pyright: ignore[reportUnknownMemberType]
        _k(backend)["occupancy"], entry, maxlen=100_000, approximate=True
    )


def occupancy(backend: str) -> list[dict[str, str]]:
    """Read the whole occupancy stream.

    Args:
        backend: Backend name.

    Returns:
        Entries, oldest first.
    """
    raw = cast(
        list[tuple[str, dict[str, str]]],
        tasks.get_valkey().xrange(_k(backend)["occupancy"]),  # pyright: ignore[reportUnknownMemberType]
    )
    return [fields for _, fields in raw]


def payload_of(task_id: str) -> Any:
    """Decode a task's payload from its hot hash.

    Args:
        task_id: The task.

    Returns:
        The payload, or None if missing.
    """
    raw = tasks.hot(task_id).get("payload")
    return json.loads(raw) if raw else None
