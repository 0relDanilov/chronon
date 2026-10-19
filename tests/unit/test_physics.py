import numpy as np

from chronon.worker import physics


def test_fit_recovers_t1_within_its_error() -> None:
    rng = np.random.default_rng(1)
    waits = physics.wait_times(200, 25)
    within = 0
    for _ in range(100):
        fit = physics.fit_t1(waits, physics.measure_t1(60.0, waits, 500, rng))
        within += abs(fit.t1_us - 60.0) <= 3 * fit.t1_err_us
    assert within >= 97  # 3 sigma covers 99.7% if the error is honest


def test_more_shots_shrink_the_error() -> None:
    rng = np.random.default_rng(2)
    waits = physics.wait_times(200, 25)
    few = physics.fit_t1(waits, physics.measure_t1(60.0, waits, 100, rng))
    many = physics.fit_t1(waits, physics.measure_t1(60.0, waits, 5000, rng))
    assert many.t1_err_us < few.t1_err_us


def test_drift_stays_bounded() -> None:
    rng = np.random.default_rng(3)
    t1 = physics.T1_MEAN_US
    for _ in range(10_000):
        t1 = physics.drift(t1, rng)
        assert physics.T1_MIN_US <= t1 <= physics.T1_MAX_US


def test_default_run_takes_two_to_three_seconds() -> None:
    waits = physics.wait_times(200, 25)
    seconds = physics.device_seconds(waits, 500) * 1.5  # default time scale
    assert 2.0 <= seconds + 0.5 + 0.2 <= 3.0  # plus reconfigure and reset
