"""The unmodified client, end to end: constructor, summary, run, state."""

import re
from collections.abc import Callable

import httpx
import pytest
from conftest import API, BACKEND, STATE
from iqcc_cloud_client.computers import IQCC_Cloud

Connect = Callable[[str], IQCC_Cloud]
Raw = Callable[[str], httpx.Client]


def _metric(text: str, name: str) -> float:
    total = 0.0
    for line in text.splitlines():
        if line.startswith(name):
            total += float(line.rsplit(" ", 1)[1])
    return total


def test_summary(connect: Connect, capsys: pytest.CaptureFixture[str]) -> None:
    summary = connect("student").summary()
    out = capsys.readouterr().out
    assert summary["online"] is True
    assert "echo" in summary["ondemand"]
    assert "SIMULATED" in summary["description"]
    assert "Latest calibration (state)" in out


def test_run_echo(connect: Connect) -> None:
    result = connect("student").run("echo", {"message": "hello chronon"})
    assert result["result"] == {"echo": {"message": "hello chronon"}}
    assert result["stderr"] == ""
    assert "contract-student" in result["stdout"]


def test_run_echo_pretty_prints(
    connect: Connect, capsys: pytest.CaptureFixture[str]
) -> None:
    result = connect("student").run(
        "echo", {"message": "pretty"}, terminal_output=True
    )
    assert result["result"]["echo"]["message"] == "pretty"
    assert "successfully executed" in capsys.readouterr().out


def test_server_side_schema_error(raw: Raw) -> None:
    r = raw("student").post(f"{API}/task/{BACKEND}/echo", json={"message": 5})
    assert r.status_code == 422
    assert "$.message" in r.json()["detail"]


def test_expired_window_is_a_readable_401(raw: Raw) -> None:
    r = raw("expired").post(f"{API}/task/{BACKEND}/echo", json={"message": "x"})
    assert r.status_code == 401
    detail = r.json()["detail"]
    assert re.search(
        r"window for backend sim-qpu is .+ → .+; it is now", detail
    )
    assert "closed" in detail


def test_expired_token_does_not_crash_the_constructor(
    connect: Connect, capsys: pytest.CaptureFixture[str]
) -> None:
    # The state service answers 401 with JSON, so the client prints it.
    qc = connect("expired")
    assert qc.summary() is None
    assert "it is now" in capsys.readouterr().out


def test_push_requires_calibrator(raw: Raw) -> None:
    r = raw("student").post(
        f"{STATE}/{BACKEND}/state/",
        json={"type": "contract", "data": {}, "comment": "", "parent_id": None},
    )
    assert r.status_code == 403
    assert "calibrator" in r.json()["detail"]


def test_reserved_type_refused(raw: Raw) -> None:
    r = raw("calibrator").post(
        f"{STATE}/{BACKEND}/state/",
        json={
            "type": "qmm_capabilities",
            "data": {},
            "comment": "",
            "parent_id": None,
        },
    )
    assert r.status_code == 403
    assert "reserved" in r.json()["detail"]


def test_lineage_and_trend(
    connect: Connect, capsys: pytest.CaptureFixture[str]
) -> None:
    qc = connect("calibrator")
    parent = qc.state.push("contract_cal", {"qubits": [{"t1": 50.5}]}, "first")
    child = qc.state.push(
        "contract_cal", {"qubits": [{"t1": 61.25}]}, "second", parent.id
    )
    assert child.parent_id == parent.id
    children = qc.state.list_children(parent.id, datatype="contract_cal")
    assert [c.id for c in children] == [child.id]
    latest = qc.state.get_latest("contract_cal")
    assert latest is not None and latest.id == child.id

    points = qc.state.trend(
        "$.qubits[0].t1", datatype="contract_cal", limit=2, terminal_output=True
    )
    assert [p["value"] for p in points] == [
        61.25,
        50.5,
    ]  # scalars, newest first
    assert "Suppressing terminal plot" not in capsys.readouterr().out


def test_errors_are_json(raw: Raw) -> None:
    c = raw("student")
    for r in (
        c.get(f"{STATE}/{BACKEND}/state/999999999"),
        c.get(f"{API}/task/{BACKEND}/00000000-0000-0000-0000-000000000000"),
        c.get(f"{STATE}/no-such-backend/state/"),
        c.get(f"{STATE}/{BACKEND}/timeseries/", params={"jsonpath": "$$bad"}),
    ):
        assert r.status_code >= 400
        assert isinstance(r.json()["detail"], str)


def test_polls_are_served_from_valkey(connect: Connect, raw: Raw) -> None:
    c = raw("student")
    before = c.get(f"{API}/metrics").text
    connect("student").run("echo", {"message": "count me"})
    after = c.get(f"{API}/metrics").text
    assert _metric(after, "chronon_poll_total") > _metric(
        before, "chronon_poll_total"
    )
    assert _metric(after, 'chronon_db_reads_total{path="poll"}') == _metric(
        before, 'chronon_db_reads_total{path="poll"}'
    )
