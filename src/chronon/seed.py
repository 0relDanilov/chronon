"""Seed the state service: ``python -m chronon.seed`` (Argo CD PostSync hook).

Idempotent. For each backend it writes:

- a new ``summary`` dataset only if the definition in chronon.backends changed;
- an initial ``state`` dataset only if none exists, because the client's
  ``summary()`` reads the latest ``state`` whenever the summary lists that type
  (computers.py:679-685) and crashes if there is none.
"""

import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from chronon.backends import BACKENDS
from chronon.db import DatasetRow, get_engine, migrate

PRODUCER = "chronon-seed"

# A plausible starting point for the simulated device; replaced by the first
# `calibrate` run. Synthetic, and labelled so.
INITIAL_STATE: dict[str, dict[str, Any]] = {
    "sim-qpu": {
        "qubits": [{"t1": 60.0, "t1_err": None, "last_calibrated": None}]
    },
}


def _latest(s: Session, backend: str, type_: str) -> DatasetRow | None:
    return s.scalars(
        select(DatasetRow)
        .where(DatasetRow.backend == backend, DatasetRow.type == type_)
        .order_by(DatasetRow.timestamp.desc(), DatasetRow.id.desc())
        .limit(1)
    ).first()


def seed() -> list[str]:
    """Write missing or changed seed datasets.

    Returns:
        One line per dataset written.
    """
    written: list[str] = []
    with Session(get_engine()) as s, s.begin():
        for name, backend in BACKENDS.items():
            summary = backend.summary()
            current = _latest(s, name, "summary")
            if current is None or current.data != summary:
                s.add(
                    DatasetRow(
                        backend=name,
                        type="summary",
                        comment="backend summary (chronon-seed)",
                        producer=PRODUCER,
                        parent_id=current.id if current else None,
                        data=summary,
                    )
                )
                written.append(f"{name}: summary")
            initial = INITIAL_STATE.get(name)
            if initial is not None and _latest(s, name, "state") is None:
                stamp = datetime.now(UTC).isoformat()
                s.add(
                    DatasetRow(
                        backend=name,
                        type="state",
                        comment="initial state (synthetic, not measured)",
                        producer=PRODUCER,
                        data={"seeded_at": stamp, **initial},
                    )
                )
                written.append(f"{name}: initial state")
    return written


if __name__ == "__main__":
    start = time.time()
    migrate()
    lines = seed() or ["nothing to do"]
    for line in lines:
        print(line)
    print(f"seed done in {time.time() - start:.1f} s")
