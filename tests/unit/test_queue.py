"""Queue semantics, against the real Lua scripts in an in-memory Valkey."""

import itertools
from typing import Any

import fakeredis
import pytest

from chronon import queue, tasks

B = "sim-qpu"


@pytest.fixture(autouse=True)
def fake_valkey(monkeypatch: pytest.MonkeyPatch) -> fakeredis.FakeRedis:
    r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(tasks, "get_valkey", lambda: r)

    # No Postgres in unit tests: return the hot fields, skip the row.
    def new_task(
        task_id: str, backend: str, workflow: str, user_id: str, payload: Any
    ) -> dict[str, str]:
        return {
            "status": "PENDING",
            "user": user_id,
            "backend": backend,
            "workflow": workflow,
            "payload": "{}",
            "result": "{}",
        }

    monkeypatch.setattr(tasks, "new_task", new_task)
    monkeypatch.setattr(tasks, "delete_durable", lambda task_id: None)
    monkeypatch.setattr(tasks, "set_status", lambda *a, **k: None)
    return r


_ids = itertools.count()


def _submit(user: str, cap: int = queue.USER_CAP) -> str:
    task_id = f"{user}-{next(_ids)}"
    queue.submit(task_id, B, "t1", user, {}, cap=cap)
    return task_id


def _drain() -> list[str]:
    order: list[str] = []
    while (t := queue.pop(B)) is not None:
        order.append(t.rsplit("-", 1)[0])
        queue.done(B, t)
    return order


def test_fair_round_robin_beats_a_greedy_user() -> None:
    # The greedy user queues 20 first (no cap here), then 5 users queue 1 each.
    for _ in range(20):
        _submit("greedy", cap=100)
    for u in range(5):
        _submit(f"s{u}")
    order = _drain()
    # Fair: everyone's single run is done within the first 2 rounds.
    assert set(order[:10]) >= {f"s{u}" for u in range(5)}
    assert max(order.index(f"s{u}") for u in range(5)) <= 9
    assert order.count("greedy") == 20


def test_fifo_serves_in_arrival_order() -> None:
    queue.set_mode(B, "fifo")
    for _ in range(20):
        _submit("greedy")
    for u in range(5):
        _submit(f"s{u}")
    order = _drain()
    assert order[:20] == ["greedy"] * 20  # the cohort waits behind all 20
    assert order[20:] == [f"s{u}" for u in range(5)]


def test_fair_mode_caps_queued_runs_per_user() -> None:
    for _ in range(queue.USER_CAP):
        _submit("greedy")
    with pytest.raises(queue.QueueFull, match="5 runs queued"):
        _submit("greedy")
    _submit("other")  # other users aren't affected
    # Once one of greedy's runs is taken by the device, it may queue again.
    queue.pop(B)
    _submit("greedy")


def test_fifo_has_no_cap() -> None:
    queue.set_mode(B, "fifo")
    for _ in range(queue.USER_CAP + 3):
        _submit("greedy")


def test_switching_mode_strands_nothing() -> None:
    a = _submit("alice")  # fair structures
    queue.set_mode(B, "fifo")
    b = _submit("bob")  # fifo list
    popped = {queue.pop(B), queue.pop(B)}
    assert popped == {a, b}
    assert queue.pop(B) is None


def test_revoke_pending_removes_from_queue() -> None:
    t = _submit("alice")
    _submit("bob")
    assert queue.revoke(B, t).value == "REVOKED"
    assert _drain() == ["bob"]


def test_crashed_worker_tasks_are_requeued(
    fake_valkey: fakeredis.FakeRedis,
) -> None:
    t = _submit("alice")
    fake_valkey.hset(tasks.task_key(t), mapping={"user": "alice"})
    assert queue.pop(B) == t  # now in the processing list; worker "dies"
    assert queue.pop(B) is None
    assert queue.requeue_processing(B) == [t]
    assert queue.pop(B) == t
