"""One T1 run in a fresh process: the pod-per-run side of ADR-0004.

The first line printed is the process start time, before any heavy import,
so the overhead measurement can see how long a pod takes to *start* doing
work. Then it runs the same device lifecycle as the warm worker:
reconfigure → run → reset. Synthetic, like the warm worker.
"""

import time

print(f"CHRONON_START {time.time():.6f}", flush=True)

import json  # noqa: E402
import sys  # noqa: E402

from chronon.worker.simqpu import RECONFIGURE_S, RESET_S, Device  # noqa: E402


def main() -> None:
    """Run one default T1 and print its result as one JSON line."""
    imported = time.time()
    time.sleep(RECONFIGURE_S)
    run = Device().t1_run({"qubit": 0})
    time.sleep(RESET_S)
    print(
        json.dumps(
            {
                "imported_at": imported,
                "finished_at": time.time(),
                "t1_us": run["t1_us"],
                "device_s": run["_device_s"],
            }
        ),
        flush=True,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
