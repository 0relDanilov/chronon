import argparse
import logging
import os

import pyvisa
from pyvisa.resources import Resource
from qm import QmJob, QuantumMachinesManager


def get_qm_job() -> QmJob:
    parser = argparse.ArgumentParser(
        prog="Synchronous hook programme",
        description="Executes in synchronously with the main QUA program",
        epilog="Useful for hybrid workflows",
    )

    parser.add_argument("-j", "--jobId")
    parser.add_argument("-q", "--qmId")
    parser.add_argument("-i", "--ip")
    parser.add_argument("-p", "--port")
    args = parser.parse_args()
    qmm = QuantumMachinesManager(
        host=args.ip, port=args.port, log_level=logging.ERROR
    )
    qm = qmm.get_qm(machine_id=args.qmId)
    job = qm.get_job(args.jobId)
    return job


def get_visa_client(instrument_name: str) -> Resource:
    e = os.getenv("IQCC_RESOURCES", "").split(",")
    if e == [""]:
        e = []
    resources = {}
    for resource in e:
        split = resource.index(":")
        resources[resource[:split]] = resource[split + 1 :]
    if instrument_name not in resources.keys():
        raise ValueError(
            f"{instrument_name} not available as runtime resource\nAvailable resources: {list(resources.keys())}"
        )
    return pyvisa.ResourceManager().open_resource(resources[instrument_name])
