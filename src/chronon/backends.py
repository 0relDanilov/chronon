"""What each backend offers: its workflows and the summary the client reads.

The seed job writes ``summary()`` into the state service; the API validates
submissions against the same schemas. One definition, two readers.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

Executor = Literal["inline", "device"]


@dataclass(frozen=True)
class Workflow:
    """An on-demand workflow.

    Attributes:
        name: Path segment in ``POST /task/{backend}/{name}``.
        description: Shown by the client's ``run()`` listing.
        schema: JSON Schema for the payload (validated client- and server-side).
        executor: ``inline`` runs in the API process; ``device`` queues for the
            backend's worker.
        role: A role the token must carry, if any.
    """

    name: str
    description: str
    schema: dict[str, Any]
    executor: Executor
    role: str | None = None


@dataclass(frozen=True)
class Backend:
    """A backend and its workflows."""

    name: str
    description: str
    state_types: dict[str, str]
    workflows: dict[str, Workflow] = field(default_factory=dict[str, Workflow])

    def summary(self, online: bool = True) -> dict[str, Any]:
        """Build the ``summary`` dataset the client reads (computers.py:650).

        Args:
            online: Whether the backend reports itself online.

        Returns:
            The summary ``data`` object.
        """
        return {
            "online": online,
            "description": self.description,
            "state": {
                k: {"description": v} for k, v in self.state_types.items()
            },
            "ondemand": {
                w.name: {"description": w.description, "schema": w.schema}
                for w in self.workflows.values()
            },
            "runtime": {"visa": {}},
        }


ECHO = Workflow(
    name="echo",
    description=(
        "Returns its payload. Runs inline in the API and never touches the "
        "device; used by the contract test."
    ),
    schema={
        "type": "object",
        "properties": {"message": {"type": "string", "maxLength": 1000}},
        "required": ["message"],
        "additionalProperties": False,
    },
    executor="inline",
)

_T1_PROPERTIES: dict[str, Any] = {
    "max_wait_us": {
        "type": "number",
        "minimum": 1,
        "maximum": 1000,
        "default": 200,
        "description": "Longest wait between excitation and readout (µs).",
    },
    "points": {
        "type": "integer",
        "minimum": 5,
        "maximum": 60,
        "default": 25,
        "description": "Number of wait times, evenly spaced from 0.",
    },
    "shots": {
        "type": "integer",
        "minimum": 50,
        "maximum": 5000,
        "default": 500,
        "description": "Repetitions per wait time.",
    },
}

T1 = Workflow(
    name="t1",
    description=(
        "T1 (energy relaxation) measurement on the simulated qubit: excite, "
        "wait, read out, fit an exponential decay. Synthetic data."
    ),
    schema={
        "type": "object",
        "properties": {
            "qubit": {"type": "integer", "minimum": 0, "maximum": 0},
            **_T1_PROPERTIES,
        },
        "required": ["qubit"],
        "additionalProperties": False,
    },
    executor="device",
)

CALIBRATE = Workflow(
    name="calibrate",
    description=(
        "Measure T1 and publish a new 'state' dataset linked to the previous "
        "one. Requires the calibrator role. Synthetic data."
    ),
    schema={
        "type": "object",
        "properties": _T1_PROPERTIES,
        "additionalProperties": False,
    },
    executor="device",
    role="calibrator",
)

SIM_QPU = Backend(
    name="sim-qpu",
    description=(
        "sim-qpu: a SIMULATED single-qubit device for the chronon learning "
        "project. All results, timings and fridge readings are synthetic."
    ),
    state_types={
        "state": "Latest calibration of the simulated device: T1 per qubit, "
        "in microseconds (synthetic).",
    },
    workflows={w.name: w for w in (ECHO, T1, CALIBRATE)},
)

BACKENDS: dict[str, Backend] = {SIM_QPU.name: SIM_QPU}
