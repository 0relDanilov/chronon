from chronon.backends import BACKENDS, ECHO
from chronon.schema import first_error


def test_echo_payload_valid() -> None:
    assert first_error(ECHO.schema, {"message": "hi"}) is None


def test_echo_payload_errors_name_the_path() -> None:
    err = first_error(ECHO.schema, {"message": 5})
    assert err is not None and err.startswith("$.message:")
    assert first_error(ECHO.schema, {}) is not None
    assert "Additional properties" in (
        first_error(ECHO.schema, {"message": "x", "y": 1}) or ""
    )


def test_summary_shape_matches_client() -> None:
    # Keys the client indexes without .get (computers.py:664-729).
    s = BACKENDS["sim-qpu"].summary()
    assert {"online", "description", "state", "ondemand", "runtime"} <= s.keys()
    assert s["runtime"]["visa"] == {}
    assert "state" in s["state"]
    for w in s["ondemand"].values():
        assert {"description", "schema"} <= w.keys()
    assert "SIMULATED" in s["description"]
