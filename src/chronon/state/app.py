"""State service: datasets, lineage and time series under /{backend}/.

Paths, query names and ordering follow docs/contract.md (state.py in the
client): trailing slashes on ``/state/`` and ``/timeseries/``; the filter is
``datatype`` except on ``/children``, where it is ``type``; newest first.
"""

import typing
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import ColumnElement, cast, func, select
from sqlalchemy.dialects.postgresql import JSONPATH
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from chronon.auth import Principal
from chronon.backends import BACKENDS
from chronon.contract import (
    RESERVED_DATASET_TYPES,
    Dataset,
    DatasetIn,
    DatasetMeta,
    TimeSeriesPoint,
)
from chronon.db import DatasetRow, get_engine
from chronon.web import install_json_errors, principal

app = FastAPI(title="chronon-state")
install_json_errors(app)

Caller = Annotated[Principal, Depends(principal)]
Skip = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=1000)]


def _meta(row: DatasetRow) -> DatasetMeta:
    return DatasetMeta(
        id=row.id,
        timestamp=row.timestamp,
        type=row.type,
        comment=row.comment,
        producer=row.producer,
        parent_id=row.parent_id,
    )


def _full(row: DatasetRow) -> Dataset:
    return Dataset(
        **_meta(row).model_dump(), backend=row.backend, data=row.data
    )


def _known(backend: str) -> None:
    if backend not in BACKENDS:
        known = ", ".join(sorted(BACKENDS))
        raise HTTPException(
            404, f"Unknown backend '{backend}'. Known backends: {known}."
        )


def _where(
    backend: str, datatype: str | None, producer: str | None
) -> list[ColumnElement[bool]]:
    conds = [DatasetRow.backend == backend]
    if datatype is not None:
        conds.append(DatasetRow.type == datatype)
    if producer is not None:
        conds.append(DatasetRow.producer == producer)
    return conds


_NEWEST_FIRST = (DatasetRow.timestamp.desc(), DatasetRow.id.desc())


def _filtered(backend: str, datatype: str | None, producer: str | None):  # noqa: ANN202
    return (
        select(DatasetRow)
        .where(*_where(backend, datatype, producer))
        .order_by(*_NEWEST_FIRST)
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Report that the process is up.

    Returns:
        A fixed status document.
    """
    return {"status": "ok"}


@app.get("/{backend}/state/")
def list_datasets(
    backend: str,
    caller: Caller,
    skip: Skip = 0,
    limit: Limit = 10,
    datatype: str | None = None,
    producer: str | None = None,
) -> list[DatasetMeta]:
    """List datasets, newest first (state.py:33-95).

    Args:
        backend: Backend name.
        caller: The verified token.
        skip: Skip the first N.
        limit: At most N.
        datatype: Only this dataset type.
        producer: Only datasets by this user.

    Returns:
        Dataset metadata, newest first.
    """
    _known(backend)
    with Session(get_engine()) as s:
        rows = s.scalars(
            _filtered(backend, datatype, producer).offset(skip).limit(limit)
        )
        return [_meta(r) for r in rows]


@app.get("/{backend}/state/{dataset_id}")
def get_dataset(backend: str, dataset_id: int, caller: Caller) -> Dataset:
    """Return one dataset with its data (state.py:133-156).

    Args:
        backend: Backend name.
        dataset_id: The dataset.
        caller: The verified token.

    Returns:
        The dataset.

    Raises:
        HTTPException: 404 if it doesn't exist on this backend.
    """
    _known(backend)
    with Session(get_engine()) as s:
        row = s.get(DatasetRow, dataset_id)
        if row is None or row.backend != backend:
            raise HTTPException(
                404, f"No dataset {dataset_id} on backend {backend}."
            )
        return _full(row)


@app.post("/{backend}/state/")
def push_dataset(backend: str, body: DatasetIn, caller: Caller) -> Dataset:
    """Store a new dataset; ``calibrator`` role only (state.py:97-131).

    Returns 200, not 201: the client treats anything but 200 as an error.

    Args:
        backend: Backend name.
        body: The dataset.
        caller: The verified token.

    Returns:
        The stored dataset.

    Raises:
        HTTPException: 403 for reserved types, 422 for a bad parent.
    """
    _known(backend)
    caller.require_role("calibrator", "Pushing datasets")
    if body.type in RESERVED_DATASET_TYPES:
        raise HTTPException(
            403,
            f"Dataset type '{body.type}' is reserved: clients act on it "
            f"(deserialize or encrypt to it), so only the operators may "
            f"write it.",
        )
    with Session(get_engine()) as s, s.begin():
        if body.parent_id is not None:
            parent = s.get(DatasetRow, body.parent_id)
            if parent is None or parent.backend != backend:
                raise HTTPException(
                    422,
                    f"parent_id {body.parent_id} isn't a dataset on backend "
                    f"{backend}; a parent must belong to the same backend.",
                )
        row = DatasetRow(
            backend=backend,
            type=body.type,
            comment=body.comment,
            producer=caller.user_id[:60],
            parent_id=body.parent_id,
            data=body.data,
        )
        s.add(row)
        s.flush()
        s.refresh(row)
        return _full(row)


@app.get("/{backend}/state/{dataset_id}/children")
def list_children(
    backend: str,
    dataset_id: int,
    caller: Caller,
    skip: Skip = 0,
    limit: Limit = 10,
    type: str | None = None,  # noqa: A002 - the client sends `type` here
    producer: str | None = None,
) -> list[DatasetMeta]:
    """List a dataset's children, newest first (state.py:298-362).

    Args:
        backend: Backend name.
        dataset_id: The parent.
        caller: The verified token.
        skip: Skip the first N.
        limit: At most N.
        type: Only this dataset type (named ``type`` by the client here).
        producer: Only datasets by this user.

    Returns:
        Child dataset metadata.
    """
    _known(backend)
    q = _filtered(backend, type, producer).where(
        DatasetRow.parent_id == dataset_id
    )
    with Session(get_engine()) as s:
        return [_meta(r) for r in s.scalars(q.offset(skip).limit(limit))]


def _unwrap(values: Any) -> Any:
    # The client plots only int/float values (state.py:199), so one match is
    # returned as a scalar rather than a one-element list.
    if isinstance(values, list):
        items = typing.cast(list[Any], values)
        if len(items) == 1:
            return items[0]
    return typing.cast(Any, values)


@app.get("/{backend}/timeseries/")
def timeseries(
    backend: str,
    caller: Caller,
    jsonpath: Annotated[str, Query(min_length=1)],
    skip: Skip = 0,
    limit: Limit = 10,
    datatype: str | None = None,
    producer: str | None = None,
) -> list[TimeSeriesPoint]:
    """Evaluate a jsonpath across datasets, newest first (state.py:158-215).

    Args:
        backend: Backend name.
        caller: The verified token.
        jsonpath: A Postgres jsonpath, e.g. ``$.qubits[0].t1``.
        skip: Skip the first N datasets.
        limit: At most N datasets.
        datatype: Only this dataset type.
        producer: Only datasets by this user.

    Returns:
        ``{id, t, value}`` per dataset.

    Raises:
        HTTPException: 422 if the jsonpath doesn't parse.
    """
    _known(backend)
    value = func.jsonb_path_query_array(
        DatasetRow.data, cast(jsonpath, JSONPATH)
    )
    q = (
        select(DatasetRow.id, DatasetRow.timestamp, value.label("value"))
        .where(*_where(backend, datatype, producer))
        .order_by(*_NEWEST_FIRST)
        .offset(skip)
        .limit(limit)
    )
    try:
        with Session(get_engine()) as s:
            rows = s.execute(q).all()
    except DBAPIError as e:
        raise HTTPException(
            422,
            f"jsonpath {jsonpath!r} couldn't be evaluated: "
            f"{str(e.orig).splitlines()[0]}",
        ) from e
    return [
        TimeSeriesPoint(id=r.id, t=r.timestamp, value=_unwrap(r.value))
        for r in rows
    ]
