"""Task API: submit, poll and revoke tasks under /task/{backend}/.

The polling hot path reads only Valkey. ``chronon_poll_total`` counts polls
and ``chronon_db_reads_total{path="poll"}`` counts the rare fallbacks to
Postgres, so "N polls, 0 DB reads" is a measured claim.
"""

import uuid
from typing import Annotated, Any

from fastapi import Body, Depends, FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

from chronon import queue, schema, tasks
from chronon.auth import Principal
from chronon.backends import BACKENDS, Workflow
from chronon.contract import (
    TERMINAL,
    TaskCreated,
    TaskState,
    TaskStatus,
    result_json,
)
from chronon.web import install_json_errors, principal

app = FastAPI(title="chronon-api")
install_json_errors(app)

Caller = Annotated[Principal, Depends(principal)]

POLLS = Counter("chronon_poll", "Task status polls served", ["backend"])
DB_READS = Counter(
    "chronon_db_reads", "Postgres reads made by the task API", ["path"]
)
SUBMITS = Counter("chronon_submit", "Tasks accepted", ["backend", "workflow"])


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Report that the process is up.

    Returns:
        A fixed status document.
    """
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    """Prometheus metrics.

    Returns:
        The text exposition format.
    """
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _workflow(backend: str, name: str) -> Workflow:
    b = BACKENDS.get(backend)
    if b is None:
        known = ", ".join(sorted(BACKENDS))
        raise HTTPException(
            404, f"Unknown backend '{backend}'. Known backends: {known}."
        )
    if name == "qua":
        raise HTTPException(
            404,
            "execute() (QUA programs) isn't supported by chronon; use "
            "run(<workflow>, payload) with a workflow from summary().",
        )
    w = b.workflows.get(name)
    if w is None:
        known = ", ".join(sorted(b.workflows))
        raise HTTPException(
            404,
            f"Backend {backend} has no workflow '{name}'. Available: {known}.",
        )
    return w


def _validate(w: Workflow, payload: Any) -> Any:
    error = schema.first_error(w.schema, payload)
    if error is not None:
        raise HTTPException(
            422, f"Payload for workflow '{w.name}' is invalid at {error}"
        )
    return payload


@app.post("/task/{backend}/{workflow}")
def submit(
    backend: str,
    workflow: str,
    payload: Annotated[Any, Body()],
    caller: Caller,
) -> TaskCreated:
    """Accept a workflow run (computers.py:356-397).

    Returns 200 with ``{"task_id"}``: the client treats anything but 200 as
    an error.

    Args:
        backend: Backend name.
        workflow: Workflow name.
        payload: The JSON body: the workflow payload.
        caller: The verified token.

    Returns:
        The new task's id.

    Raises:
        HTTPException: 404 unknown backend/workflow, 422 schema violation.
    """
    w = _workflow(backend, workflow)
    if w.role is not None:
        caller.require_role(w.role, f"Running '{workflow}'")
    payload = _validate(w, payload)

    task_id = str(uuid.uuid4())
    if w.executor == "inline":
        _run_inline(task_id, backend, w, caller, payload)
    else:
        try:
            queue.submit(task_id, backend, w.name, caller.user_id, payload)
        except queue.QueueFull as e:
            raise HTTPException(429, str(e)) from e
    SUBMITS.labels(backend, workflow).inc()
    return TaskCreated(task_id=task_id)


def _run_inline(
    task_id: str, backend: str, w: Workflow, caller: Principal, payload: Any
) -> None:
    if w.name != "echo":
        raise HTTPException(500, f"No inline executor for '{w.name}'.")
    result = result_json(
        {"echo": payload}, stdout=f"echo for {caller.user_id}: {payload}\n"
    )
    tasks.create(
        task_id,
        backend,
        w.name,
        caller.user_id,
        payload,
        status=TaskStatus.SUCCESS,
        result=result,
    )


def _owned_state(
    backend: str, task_id: str, caller: Principal, *, count: bool = True
) -> TaskState:
    if count:
        POLLS.labels(backend).inc()
    hot = tasks.hot(task_id)
    if hot:
        if hot.get("backend") != backend or hot.get("user") != caller.user_id:
            raise HTTPException(404, f"No task {task_id} on backend {backend}.")
        return TaskState(
            task_status=TaskStatus(hot["status"]),
            task_result=hot.get("result", "{}"),
        )
    DB_READS.labels("poll" if count else "revoke").inc()
    row = tasks.durable(task_id)
    if row is None or row.backend != backend or row.user_id != caller.user_id:
        raise HTTPException(404, f"No task {task_id} on backend {backend}.")
    return TaskState(task_status=TaskStatus(row.status), task_result=row.result)


@app.get("/task/{backend}/{task_id}")
def poll(backend: str, task_id: str, caller: Caller) -> TaskState:
    """Report a task's status from Valkey (computers.py:423-485).

    Args:
        backend: Backend name.
        task_id: The task.
        caller: The verified token; only the submitter sees a task.

    Returns:
        ``{"task_status", "task_result"}``.
    """
    return _owned_state(backend, task_id, caller)


@app.delete("/task/{backend}/{task_id}")
def revoke(backend: str, task_id: str, caller: Caller) -> TaskState:
    """Revoke a task (the client's Ctrl-C handler, computers.py:399-408).

    A pending task leaves the queue and becomes REVOKED. A running one gets a
    revoke flag that the worker checks between runs.

    Args:
        backend: Backend name.
        task_id: The task.
        caller: The verified token; only the submitter may revoke.

    Returns:
        The task's status after the request.
    """
    state = _owned_state(backend, task_id, caller, count=False)
    if state.task_status in TERMINAL:
        return state
    status = queue.revoke(backend, task_id)
    return TaskState(task_status=status, task_result=state.task_result)
