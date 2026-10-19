"""Synthetic physics for the simulated device (T1 decay) and its fit.

Everything here is SYNTHETIC: a stand-in for a real qubit, good enough to make
the platform behave like one (runs take time, results are noisy, calibration
drifts), and nothing more.

The model: a qubit prepared in |1> decays to |0> with lifetime T1, so after
waiting t it is still excited with probability exp(-t / T1). Each shot is one
Bernoulli draw, and the readout misreports the state with probability
``READOUT_ERROR``. Fitting A * exp(-t / T1) + B to the measured excited
fraction recovers T1, with an uncertainty that shrinks as shots grow.
"""

import math
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import curve_fit  # pyright: ignore[reportUnknownVariableType, reportMissingTypeStubs]

READOUT_ERROR = 0.02
READOUT_US = 1.0
RESET_US = 10.0
T1_MEAN_US = 60.0
T1_MIN_US, T1_MAX_US = 40.0, 80.0
DRIFT_STEP_US = 0.4


def drift(t1_us: float, rng: np.random.Generator) -> float:
    """Advance the hidden true T1 one step of a bounded random walk.

    A gentle pull toward the mean keeps it from wandering off over a night.

    Args:
        t1_us: The current true T1.
        rng: Random source.

    Returns:
        The next true T1, within [40, 80] µs.
    """
    pull = 0.02 * (T1_MEAN_US - t1_us)
    nxt = t1_us + pull + float(rng.normal(0.0, DRIFT_STEP_US))
    return min(T1_MAX_US, max(T1_MIN_US, nxt))


def wait_times(max_wait_us: float, points: int) -> NDArray[np.float64]:
    """Evenly spaced wait times from 0 to ``max_wait_us``.

    Args:
        max_wait_us: The longest wait.
        points: How many waits.

    Returns:
        The waits in µs.
    """
    return np.linspace(0.0, max_wait_us, points)


def device_seconds(waits_us: NDArray[np.float64], shots: int) -> float:
    """Device time a T1 run occupies: every shot waits, reads out, resets.

    Args:
        waits_us: The wait times.
        shots: Shots per wait time.

    Returns:
        Seconds of (simulated) device time, before any time scaling.
    """
    per_shot_us = waits_us + READOUT_US + RESET_US
    return float(per_shot_us.sum()) * shots * 1e-6


def measure_t1(
    true_t1_us: float,
    waits_us: NDArray[np.float64],
    shots: int,
    rng: np.random.Generator,
) -> NDArray[np.float64]:
    """Simulate the measured excited-state fraction at each wait time.

    Args:
        true_t1_us: The hidden T1.
        waits_us: Wait times.
        shots: Shots per wait time.
        rng: Random source.

    Returns:
        The fraction of shots read as |1> at each wait.
    """
    p_excited = np.exp(-waits_us / true_t1_us)
    # Readout flips the outcome with probability READOUT_ERROR.
    p_read_1 = p_excited * (1 - READOUT_ERROR) + (1 - p_excited) * READOUT_ERROR
    ones = rng.binomial(shots, p_read_1)
    return ones / shots


def _decay(t: Any, a: float, t1: float, b: float) -> Any:
    return a * np.exp(-t / t1) + b


@dataclass(frozen=True)
class T1Fit:
    """A fitted T1 curve with one-sigma uncertainties."""

    t1_us: float
    t1_err_us: float
    amplitude: float
    offset: float


def fit_t1(
    waits_us: NDArray[np.float64], excited: NDArray[np.float64]
) -> T1Fit:
    """Fit A * exp(-t / T1) + B.

    Args:
        waits_us: Wait times.
        excited: Measured excited fraction at each wait.

    Returns:
        The fit; the error is the square root of the covariance diagonal.
    """
    guess_t1 = max(float(waits_us[-1]) / 3, 1.0)
    popt, pcov = cast(
        tuple[NDArray[np.float64], NDArray[np.float64]],
        curve_fit(
            _decay,
            waits_us,
            excited,
            p0=(0.95, guess_t1, 0.02),
            bounds=((0.0, 1e-3, -0.2), (1.5, 1e4, 0.5)),
            maxfev=10_000,
        ),
    )
    errs = np.sqrt(np.diag(pcov))
    t1_err = float(errs[1])
    return T1Fit(
        t1_us=float(popt[1]),
        t1_err_us=t1_err if math.isfinite(t1_err) else float("nan"),
        amplitude=float(popt[0]),
        offset=float(popt[2]),
    )
