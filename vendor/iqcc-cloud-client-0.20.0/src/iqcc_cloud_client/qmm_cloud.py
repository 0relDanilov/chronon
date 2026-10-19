import os
import sys
from typing import Any

import numpy as np
from qm import DictQuaConfig, Program

from iqcc_cloud_client.computers import IQCC_Cloud


class Capabilities:
    def supports(self, capability: Any) -> bool:
        return False


class CloudJob:
    def __init__(self, run_data: dict):
        self._run_data = run_data
        self.result_handles = CloudResultHandles(self._run_data["result"])

    def execution_report(self):
        """
        This is a placeholder for the execution_report method to not break api of qualibration_libs (which does not assumes cloud results object).
        It is used to display the execution report.
        """
        return None

    @property
    def id(self):
        return ""

    @property
    def status(self):
        return "completed"


class CloudQuantumMachine:
    def __init__(self, backend: str, config: DictQuaConfig):
        """_summary_

        Args:
            backend (str): IQCC backend name
            config (DictQuaConfig):  QUA config
        """
        self._qc = IQCC_Cloud(quantum_computer_backend=backend)
        self._config = config

    def execute(
        self, program: Program, terminal_output: bool = False, options={}
    ) -> CloudJob:
        """_summary_

        Args:
            program (Program): QUA program
            terminal_output (bool, optional): Passing to [iqcc_cloud_client.IQCC_Cloud](). Defaults to False.
            options (dict, optional): Passing to [iqcc_cloud_client.IQCC_Cloud]() options. Defaults to {}.

        Returns:
            CloudJob: _description_
        """
        timeout_in_s = os.getenv("IQCC_DEFAULT_TIMEOUT", 60)
        if "timeout" not in options.keys():
            options["timeout"] = timeout_in_s
        run_data = self._qc.execute(
            program,
            self._config,
            terminal_output=terminal_output,
            options=options,
        )
        # pass stdout and stderr as the standard QUA client would print
        if "stdout" in run_data.keys():
            print(run_data["stdout"])
        if "stderr" in run_data.keys():
            print(run_data["stderr"], file=sys.stderr)
        self.job = CloudJob(run_data)
        return self.job

    def get_running_job(self) -> CloudJob:
        if self.job.result_handles.is_processing():
            return self.job
        else:
            return None

    def get_jobs(self, status):
        """dummy method to not break api of qualang_tools.multi_user.multi_user_tools version 0.19.4"""
        return False

    def close(self):
        pass


class CloudResultHandles:
    def __init__(self, results_dict: dict):
        self._results_dict = results_dict
        self._is_processing = True
        for result in results_dict:
            setattr(self, result, results_dict[result])

    def is_processing(self):
        is_processing = self._is_processing
        if is_processing:
            self._is_processing = False
        return is_processing

    def wait_for_all_values(self):
        pass

    def keys(self):
        return self._results_dict.keys()

    def get(self, handle: str):
        return CloudResult(self._results_dict[handle])

    def fetch_results(self, *args, **kwargs):
        """Fetch results from the specified streams"""

        for data, res in self._results_dict.items():
            self._results_dict[data] = self._format(res)

        return CloudFetchedResults(self._results_dict)

    def _format(self, data):
        if type(data) is np.ndarray:
            if type(data[0]) is np.void:
                if len(data.dtype) == 1:
                    data = data["value"]
        return data


class CloudFetchedResults:
    """Returned by CloudResultHandles.fetch_results().

    qualang_tools expects .get(name) to return raw data (numpy arrays),
    not CloudResult wrappers. This object satisfies that contract while
    keeping CloudResultHandles.get() returning CloudResult (needed for
    wait_for_values / count_so_far before fetching).
    """

    def __init__(self, results_dict: dict):
        self._results_dict = results_dict

    def get(self, handle: str):
        return self._results_dict[handle]


class CloudResult:
    def __init__(self, data):
        self._data = data

    def fetch_all(self):
        return self._data

    def wait_for_values(self, *args):
        pass

    def count_so_far(self):
        """
        This is a placeholder for the count_so_far method to not break api of qualibration_libs (which does not assumes cloud results object).
        It is used to check if the job is processing.
        """
        return None


class CloudQuantumMachinesManager:
    def __init__(self, backend: str):
        """Adapter class that exposes iqcc_cloud_client as QM's Quantum Machines Manager.
        This provides minimal compatibility needed to run remote cloud tasks
        with familiar QUA SDK interface.

        Args:
            backend (str): name of cloud backend
        """
        self.backend = backend
        self.capabilities = Capabilities()

    def open_qm(
        self, config: DictQuaConfig, *args, **kwargs
    ) -> CloudQuantumMachine:
        """Adapter for opening quantum machine

        Args:
            config (DictQuaConfig): QUA config

        Returns:
            CloudQuantumMachine: _description_
        """
        self._qm = CloudQuantumMachine(self.backend, config)
        return self._qm
