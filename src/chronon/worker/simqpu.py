"""sim-qpu device loop: reconfigure, run, reset (simulated device).

One long-lived worker owns the (simulated) device: the Deployment has one
replica and ``strategy: Recreate``, so two workers never hold it at once.
Each task: pop (fifo or fair, per ``sched:sim-qpu``) → STARTED → reconfigure
(0.5 s) → check the revoke flag → run → reset (0.2 s) → SUCCESS or FAILURE →
an occupancy entry. Everything the device "measures" is synthetic.
"""

import logging
import math
import os
import random
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from chronon import queue, tasks
from chronon.contract import TaskStatus, result_json
from chronon.db import DatasetRow, get_engine, migrate
from chronon.seed import seed
from chronon.worker import physics

BACKEND = "sim-qpu"
log = logging.getLogger("chronon.worker")

TIME_SCALE = float(os.environ.get("CHRONON_SIM_TIME_SCALE", "1.5"))
RECONFIGURE_S = float(os.environ.get("CHRONON_RECONFIGURE_S", "0.5"))
RESET_S = float(os.environ.get("CHRONON_RESET_S", "0.2"))
HEARTBEAT = Path(os.environ.get("CHRONON_HEARTBEAT", "/tmp/heartbeat"))
IDLE_SLEEP_S = 0.1


class Device:
    """The simulated device: a hidden, drifting T1 and a random source."""

    def __init__(self, seed_value: int | None = None) -> None:
        self.rng = np.random.default_rng(seed_value)
        self.true_t1_us = physics.T1_MEAN_US

    def t1_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Measure T1 once; sleeps for the (scaled) device time.

        Args:
            payload: Validated ``t1``/``calibrate`` payload.

        Returns:
            Wait times, populations, the fit and the device time.
        """
        self.true_t1_us = physics.drift(self.true_t1_us, self.rng)
        waits = physics.wait_times(
            float(payload.get("max_wait_us", 200)),
            int(payload.get("points", 25)),
        )
        shots = int(payload.get("shots", 500))
        device_s = physics.device_seconds(waits, shots) * TIME_SCALE
        excited = physics.measure_t1(self.true_t1_us, waits, shots, self.rng)
        time.sleep(device_s)
        fit = physics.fit_t1(waits, excited)
        return {
            "qubit": int(payload.get("qubit", 0)),
            "wait_us": [round(float(w), 4) for w in waits],
            "excited_population": [round(float(p), 5) for p in excited],
            "shots": shots,
            "t1_us": round(fit.t1_us, 3),
            "t1_err_us": None
            if math.isnan(fit.t1_err_us)
            else round(fit.t1_err_us, 3),
            "fit": {
                "model": "A*exp(-t/T1)+B",
                "amplitude": round(fit.amplitude, 4),
                "offset": round(fit.offset, 4),
            },
            "_device_s": device_s,
        }


def _publish_state(
    run: dict[str, Any], user: str, task_id: str
) -> dict[str, Any]:
    """Write a new ``state`` dataset linked to the previous one.

    Args:
        run: A finished T1 run.
        user: The calibrator.
        task_id: The task, for the comment.

    Returns:
        The new dataset's id and parent id.
    """
    now = datetime.now(UTC).isoformat()
    with Session(get_engine()) as s, s.begin():
        prev = s.scalars(
            select(DatasetRow)
            .where(DatasetRow.backend == BACKEND, DatasetRow.type == "state")
            .order_by(DatasetRow.timestamp.desc(), DatasetRow.id.desc())
            .limit(1)
        ).first()
        row = DatasetRow(
            backend=BACKEND,
            type="state",
            comment=f"calibrate {task_id[:8]} (synthetic)",
            producer=user[:60],
            parent_id=prev.id if prev else None,
            data={
                "qubits": [
                    {
                        "t1": run["t1_us"],
                        "t1_err": run["t1_err_us"],
                        "last_calibrated": now,
                    }
                ]
            },
        )
        s.add(row)
        s.flush()
        return {"state_dataset_id": row.id, "parent_id": row.parent_id}


def execute(
    device: Device,
    workflow: str,
    payload: dict[str, Any],
    user: str,
    task_id: str,
) -> str:
    """Run one task on the device and encode its result for the client.

    Args:
        device: The simulated device.
        workflow: ``t1`` or ``calibrate``.
        payload: The validated payload.
        user: The submitting user.
        task_id: The task.

    Returns:
        The ``task_result`` JSON string.

    Raises:
        ValueError: For a workflow this worker doesn't run.
    """
    started = time.time()
    run = device.t1_run(payload)
    device_s = run.pop("_device_s")
    err = run["t1_err_us"]
    err_text = f"{err:.1f}" if err is not None else "?"
    summary = f"T1 = {run['t1_us']:.1f} ± {err_text} µs"
    if workflow == "t1":
        result = run
        stdout = f"{summary} (simulated device, {run['shots']} shots/point)\n"
    elif workflow == "calibrate":
        result = {"calibration": run, **_publish_state(run, user, task_id)}
        stdout = (
            f"{summary}; published state dataset "
            f"{result['state_dataset_id']} (parent {result['parent_id']})\n"
        )
    else:
        raise ValueError(f"sim-qpu doesn't run workflow '{workflow}'")
    result["__qpu_execution_time_seconds"] = round(device_s, 4)
    result["__total_python_runtime_seconds"] = round(time.time() - started, 4)
    # The client indexes [name]["temperature_kelvin"] and ["unix_timestamp"]
    # (computers.py:613-620). Simulated, like everything else here.
    result["__fridge_info"] = {
        "mxc": {
            "temperature_kelvin": round(
                0.0118 + random.uniform(-2e-4, 2e-4), 5
            ),
            "unix_timestamp": time.time(),
        }
    }
    return result_json(result, stdout=stdout)


def handle(device: Device, task_id: str) -> None:
    """Take one popped task through the device lifecycle.

    Args:
        device: The simulated device.
        task_id: The popped task.
    """
    hot = tasks.hot(task_id)
    user, workflow = hot.get("user", "?"), hot.get("workflow", "?")
    if hot.get("status") == TaskStatus.REVOKED or queue.revoke_requested(
        task_id
    ):
        tasks.set_status(task_id, TaskStatus.REVOKED)
        queue.done(BACKEND, task_id)
        return
    tasks.set_status(task_id, TaskStatus.STARTED)
    start = time.time()
    try:
        time.sleep(RECONFIGURE_S)  # load this user's configuration
        if queue.revoke_requested(task_id):
            tasks.set_status(task_id, TaskStatus.REVOKED)
            return
        payload: dict[str, Any] = queue.payload_of(task_id) or {}
        result = execute(device, workflow, payload, user, task_id)
        tasks.set_status(task_id, TaskStatus.SUCCESS, result)
    except Exception as e:  # a failed run must never stop the device loop
        log.exception("task %s failed", task_id)
        tasks.set_status(
            task_id,
            TaskStatus.FAILURE,
            result_json(
                {},
                stderr=f"{type(e).__name__}: {e}\n"
                + traceback.format_exc(limit=3),
            ),
        )
    finally:
        time.sleep(RESET_S)  # return the device to a known state
        end = time.time()
        queue.record_occupancy(BACKEND, user, task_id, workflow, start, end)
        queue.done(BACKEND, task_id)


def main() -> None:
    """Run the device loop forever."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    migrate()
    for line in seed():
        log.info("published %s", line)
    requeued = queue.requeue_processing(BACKEND)
    if requeued:
        log.info(
            "re-queued %d task(s) left by a previous worker", len(requeued)
        )
    device = Device()
    log.info("sim-qpu worker ready (time scale %.2f)", TIME_SCALE)
    while True:
        HEARTBEAT.touch()
        task_id = queue.pop(BACKEND)
        if task_id is None:
            time.sleep(IDLE_SLEEP_S)
            continue
        handle(device, task_id)


if __name__ == "__main__":
    main()
