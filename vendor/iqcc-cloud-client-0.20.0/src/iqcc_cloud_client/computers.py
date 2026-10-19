import base64
import json
import os
import pickle
import signal
from http import HTTPStatus
from time import sleep
from typing import Union

import arrow
import httpx
import jsonschema
import jwt
import toml
from pydantic import AnyUrl
from qm import (
    DictQuaConfig,
    Program,
    QuantumMachinesManager,
    generate_qua_script,
)
from rich import print_json
from rich.console import Console
from rich.table import Table

from iqcc_cloud_client._version import __version__
from iqcc_cloud_client.state import StateService
from iqcc_cloud_client.utilities import (
    _complex_decoder,
    _convert_numpy_to_list,
    _create_payload,
    _resolve_files,
    _this_is_qua_program,
    _truncate_strings,
    format_json_dense_arrays,
)


class IQCC_Cloud(object):
    def __init__(
        self,
        quantum_computer_backend: str,
        api_token: str = None,
        url: AnyUrl = "https://cloud.i-qcc.com",
        datastore: AnyUrl | None = None,
    ):
        """Client that provides handle to remote quantum computers.

        Args:
            quantum_computer_backend (str): select quantum computer.
            api_token (str, optional): your secret API access token. If not provided will be read from `~/.config/iqcc_cloud/config.toml`
            url (_type_, optional): online access point. Defaults to "https://cloud.i-qcc.com".
            datastore (_type_, optional): online storage of the data. Set project name or project_name@datastore_URL if not using default datastore
        """
        self.console = Console(legacy_windows=False)
        if "VSCODE_PID" in os.environ or "CODE_SERVER_PARENT_PID" in os.environ:
            self.console.is_jupyter = False
            # resolve rich in VS code interactive notebook
            # https://github.com/Textualize/rich/issues/3483
            # https://github.com/microsoft/vscode-jupyter/issues/7380
        if api_token is None:
            try:
                data = toml.load(
                    os.path.join(
                        os.path.expanduser("~"),
                        ".config",
                        "iqcc_cloud",
                        "config.toml",
                    )
                )
                api_token = data["tokens"][quantum_computer_backend]
                if "url" in data.keys():
                    url = data["url"]
            except Exception:
                self.console.print("[bold red]Missing IQCC cloud API token")
                if "tokens" in data.keys():
                    all_backends = []
                    for x in data["tokens"]:
                        all_backends.append(x)
                    self.console.print(
                        f"Requested backend [bold blue]{quantum_computer_backend}[/bold blue], while existing tokens are only for {all_backends} backends."
                    )

                self.console.print(
                    ":point_right: Please provide either directly [bold blue]api_token[/bold blue], or set it up using [bold blue]iqcc-cloud setup[/bold blue] command line (terminal) command"
                )
                self.console.print(
                    ":point_right: Alternatively, verify that you typed backend name correctly."
                )
                raise ValueError("Missing IQCC cloud API token")
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "User-agent": f"iqcc-cloud-client/{__version__}",
            # "Content-Type": "application/json",
            # "Content-Encoding": "gzip",
        }
        self.token = api_token
        self.backend = quantum_computer_backend
        self.url = url
        self.data_store_url = "https://ds.i-qcc.com"
        self.data_store_project = None
        if datastore is not None:
            a = datastore.split("@")
            self.data_store_project = a[0]
            if len(a) > 1:
                self.data_store_url = a[1]
        self.timeout = 60.0  # timeout of requests
        self._summary = self.state.get_latest("summary")
        if self._summary is not None:
            self._summary = self._summary.data

        # Load the worker's ML-KEM-768 public key record for encapsulation
        try:
            key_qua = self.state.get_latest("key_qua")
            if key_qua is not None:
                self._key_record = key_qua.data
                from iqcc_shared.crypto import mlkem_public_key_from_json

                self._worker_public_key = mlkem_public_key_from_json(
                    self._key_record["current"]["public_key"],
                )
                self._worker_key_id = self._key_record["current"]["key_id"]
            else:
                self._key_record = None
                self._worker_public_key = None
                self._worker_key_id = None
        except Exception as e:
            self.console.print(
                f"[dim]Could not load key_qua: {e} (encryption disabled)[/dim]"
            )
            self._key_record = None
            self._worker_public_key = None
            self._worker_key_id = None
        self._last_session_key = None

        self._capabilities = None
        self._capabilities = self.state.get_latest("qmm_capabilities")
        if self._capabilities is not None:
            self._capabilities = pickle.loads(
                base64.b64decode(self._capabilities.data["data"])
            )

    @property
    def access_rights(self) -> dict:
        """Specifies access rights to backend for used backend token

        Returns:
            dict: dictionary `{"roles":[...], "projects":[...]}` for roles
                and project access that user has for current backend
        """
        qpu = jwt.decode(self.token, options={"verify_signature": False})[
            "qpu"
        ][self.backend]
        rights = {"roles": [], "projects": []}
        if "access" in qpu.keys():
            rights["roles"] = qpu["access"]
        if "project" in qpu.keys():
            rights["projects"] = qpu["project"]
        return rights

    def execute(
        self,
        qua_program: Union[Program, bytes, str] = None,
        qua_config: DictQuaConfig = {},
        terminal_output=False,
        debug=False,
        options: dict = {},
    ) -> dict:
        """Execute QUA program on quantum computer

        Args:
            qua_program (Union[Program, bytes, str]): QUA program. Defaults to None.
            qua_config (DictQuaConfig): QUA config. Defaults to `{}`
            terminal_output (bool, optional): Should results be pretty printed
                in terminal. Defaults to False.
            debug (bool, optional): Should final submitted code be pretty
                printed in terminal. Defaults to False.
            options (dict, optional): Backend specific options. Defaults to `{}`.

        Raises:
            ValueError: _description_

        Returns:
            _dict_: measurement results
        """
        # backend_status = self.state.get_latest("status")
        # print(backend_state)

        binary = ""

        if type(qua_program) is str:
            if _this_is_qua_program(qua_program):
                namespace = {}

                # Execute the code string within the provided namespace
                try:
                    exec(qua_program, namespace)
                except Exception as e:
                    print(f"Error executing code: {e}")
                    exit()
                qua_program = namespace["prog"]
            else:
                raise ValueError(
                    "Submitted string is not serialized qua program. Submit either serialized QUA program, or directly QUA Program object, or binary."
                )

        if qua_config != "" and qua_config != {}:
            qua_config = _convert_numpy_to_list(qua_config)
            if self._worker_public_key is not None:
                if type(qua_program) is Program:
                    qua_program: Program = qua_program
                    QuantumMachinesManager.set_capabilities_offline(
                        self._capabilities
                    )
                    binary = qua_program.to_protobuf(qua_config)
                elif type(qua_program) is bytes:
                    binary = qua_program
                else:
                    raise ValueError(
                        f"qua_program can either be of Program type of bytes type. Received {type(qua_program)} type instead."
                    )
            else:
                self.console.print(
                    "Failing back to the non E2E encrypted payload."
                )
                binary = generate_qua_script(qua_program)

        for x in options.keys():
            if x not in [
                "sync_hook",
                "pre_hook",
                "post_hook",
                "timeout",
                "profiling",
            ]:
                raise ValueError(f"{x} is not valid option")

        _resolve_files(options)
        payload = {"qua": binary, "qua_config": qua_config, "options": options}

        # Encrypt the QUA payload if the worker's public key is available
        if self._worker_public_key is not None:
            from iqcc_shared.crypto import encrypt

            message_bytes, session_key = encrypt(
                payload=payload,
                paths=["qua", "qua_config"],  # encrypt only the QUA binary
                target_public_key=self._worker_public_key,
                target_key_id=self._worker_key_id,
            )
            # Store session key for decrypting worker responses
            self._last_session_key = session_key
            # Pass encrypted message to the worker
            payload = {
                "encrypted": True,
                "message": message_bytes,
            }

        return self.__serve_request_spinner(
            "QUA program",
            payload,
            "task",
            "POST",
            terminal_output=terminal_output,
            debug=debug,
            api_path_post="qua",
        )

    def run(
        self,
        workflow: str = None,
        payload: dict = None,
        terminal_output=False,
        debug=False,
    ) -> dict:
        """Run on-demand workflow. Execute without arguments to get in stdout
        listing of available workflows.

        Args:
            workflow (str, optional): Name of workflow to run. If empty command will list options. Defaults to "".
            payload (dict, optional): Payload of the workflow. If left empty, command will print JSON schema detailing data structure for payload. Defaults to `None`.
            terminal_output (bool, optional): Should results and all outputs be pretty-printed to command line? Useful for debugging. Defaults to False.
            debug (bool, optional): More verbose debugging. Defaults to False.

        Raises:
            ValueError: if non existing workflow is requested

        Returns:
            dict: `{"stdout":str, "stderr":str, "result":dict}}`
        """
        if workflow is None:
            self._available_on_demand()
            return
        if workflow not in self._summary["ondemand"].keys():
            self._available_on_demand()
            self.console.print(
                f":point_right: Requested workflow [red bold]{workflow}[/red bold] not available on this backend"
            )
            raise ValueError(
                f'Requested workflow "{workflow}" not available on this backend'
            )
        if payload is None:
            self.console.print(
                f":point_right: Expected payload format for workflow [blue bold]{workflow}[/blue bold] is"
            )
            print_json(data=self._summary["ondemand"][workflow]["schema"])
            return
        try:
            jsonschema.validate(
                payload, schema=self._summary["ondemand"][workflow]["schema"]
            )
        except jsonschema.exceptions.ValidationError as e:
            self.console.print(
                f"[red]🚨\tError validating payload on path [bold blue]{e.json_path}[/bold blue][/red]"
            )
            self.console.print(e.message)
            self.console.print("On-demand run terminated")
            return
        request_name = f"{workflow} ondemand workflow requested"
        if "directory" in payload.keys():
            payload["directory"] = _create_payload(payload["directory"])
        data = self.__serve_request_spinner(
            request_name,
            payload,
            "task",
            "POST",
            terminal_output=terminal_output,
            debug=debug,
            api_path_post=workflow,
        )
        return data

    def __http_error_handler(self, r: httpx.Response):
        """Check if request is successful

        Args:
            r (httpx.Response): request response

        Raises:
            ConnectionError: Transport error due to networking or server not available
            ValueError: Server returned error due to issue with payload
        """
        if r.status_code != httpx.codes.OK:
            self.console.print(f"[bold red]🚨 Error code {r.status_code}")
            self.console.print(f"[bold red]{HTTPStatus(r.status_code).phrase}")
            try:
                self.console.print(f"[bold red]{r.json()['detail']}")
            except Exception as _:
                raise ConnectionError(
                    f"Error code {r.status_code} {HTTPStatus(r.status_code).phrase}"
                )
            raise ValueError(
                f"Error code {r.status_code} {HTTPStatus(r.status_code).phrase}"
            )

    def __serve_request_spinner(
        self,
        request_name: str,
        payload: dict,
        api_path: str,
        method: str,
        terminal_output=False,
        debug=False,
        options: dict = {},
        api_path_post=None,
    ) -> dict:
        timed_out = None
        with self.console.status(
            f"[bold blue]Sending {request_name} to {self.url}"
        ) as status:
            client = httpx.Client(
                headers=self.headers,
                timeout=self.timeout,
                http2=self.url != "http://localhost:8000",
                http1=False,
            )
            previous_signal_handler = None
            try:
                url = self.url + f"/{api_path}/{self.backend}"
                if api_path_post is not None:
                    url += f"/{api_path_post}"
                if method == "POST":
                    if payload.get("encrypted"):
                        r = client.post(
                            url,
                            content=payload["message"],
                            headers={
                                "Content-Type": "application/octet-stream"
                            },
                        )
                    else:
                        r = client.post(url, json=payload)
                else:
                    r = client.get(url)

                self.__http_error_handler(r)
                task_id = r.json()["task_id"]

                def signal_handler(sig, frame):
                    self.console.log(
                        "Interrupting execution on user request..."
                    )
                    client.delete(self.url + f"/task/{self.backend}/{task_id}")
                    self.console.log("Execution interrupted.")
                    self.console.print(
                        f"Task {task_id} revoked upon user request."
                    )
                    raise KeyboardInterrupt()

                try:
                    previous_signal_handler = signal.getsignal(signal.SIGINT)
                    signal.signal(signal.SIGINT, signal_handler)
                except ValueError as _:
                    pass

                self.console.log(
                    f"{request_name} submitted to [bold blue]{self.backend}[/bold blue] (id = {task_id})"
                )

                status.update(
                    status="[bold blue] Waiting for execution", spinner="earth"
                )
                try:
                    r = client.get(
                        self.url + f"/task/{self.backend}/{task_id}", timeout=10
                    )
                except httpx.ReadTimeout as _:
                    r = client.get(self.url + f"/task/{self.backend}/{task_id}")
                self.__http_error_handler(r)
                while r.json()["task_status"] == "PENDING":
                    sleep(1)
                    try:
                        r = client.get(
                            self.url + f"/task/{self.backend}/{task_id}",
                            timeout=10,
                        )
                    except httpx.ReadTimeout as _:
                        r = client.get(
                            self.url + f"/task/{self.backend}/{task_id}",
                            timeout=10,
                        )
                    except httpx.RemoteProtocolError as _:
                        client = httpx.Client(
                            headers=self.headers,
                            timeout=self.timeout,
                            http2=self.url != "http://localhost:8000",
                            http1=False,
                        )
                        r = client.get(
                            self.url + f"/task/{self.backend}/{task_id}",
                            timeout=5,
                        )
                    self.__http_error_handler(r)

                self.console.log("Execution started")
                status.update(
                    status="[bold green]Executing",
                    spinner="bouncingBall",
                    spinner_style="green",
                )
                while r.json()["task_status"] in ["RECEIVED", "STARTED"]:
                    sleep(1)
                    try:
                        r = client.get(
                            self.url + f"/task/{self.backend}/{task_id}",
                            timeout=5,
                        )
                    except httpx.ReadTimeout as _:
                        r = client.get(
                            self.url + f"/task/{self.backend}/{task_id}",
                            timeout=5,
                        )
                    except httpx.RemoteProtocolError as _:
                        client = httpx.Client(
                            headers=self.headers,
                            timeout=self.timeout,
                            http2=self.url != "http://localhost:8000",
                            http1=False,
                        )
                        r = client.get(
                            self.url + f"/task/{self.backend}/{task_id}",
                            timeout=5,
                        )
                    self.__http_error_handler(r)

                self.console.log("Execution finished")
                r = r.json()
            finally:
                client.close()
                try:
                    if previous_signal_handler is not None:
                        signal.signal(signal.SIGINT, previous_signal_handler)
                except ValueError as _:
                    pass

        raw_results = json.loads(r["task_result"], object_hook=_complex_decoder)

        # Decrypt worker response if it was encrypted
        if self._last_session_key is not None and raw_results.get("encrypted"):
            from iqcc_shared.crypto import decrypt

            msgpack_bytes = bytes.fromhex(raw_results["result"])
            results, _ = decrypt(
                message_bytes=msgpack_bytes,
                paths=["result", "stdout", "stderr"],
                session_key=self._last_session_key,
            )
            # Clean up — session key is single-use
            self._last_session_key = None
        else:
            results = raw_results

        if r["task_status"] == "SUCCESS":
            if "task_result" in r.keys():
                if "stderr" in results.keys() and results["stderr"] != "":
                    self.console.print(f"[bold red]{request_name} has error:")
                    self.console.print(f"[bold red]{results['stderr']}")
                    if "Execution timed out after" in results["stderr"]:
                        timed_out = results["stderr"]
                    if (
                        "Timeout occured while waiting for result streams"
                        in results["stderr"]
                    ):
                        timed_out = results["stderr"]
                else:
                    self.console.print(
                        f"[bold green]{request_name} successfully executed"
                    )
            else:
                self.console.print(
                    f"[bold green]{request_name} successfully executed"
                )
        else:
            self.console.print(f"[bold red]{r['task_status']}")

        if terminal_output:
            if "result" in results.keys():
                if "stdout" in results.keys() and results["stdout"] != "":
                    self.console.print("[bold blue] 👍 \tstdout:")
                    self.console.print(f"{results['stdout']}")
                if "stderr" in results.keys() and results["stderr"] != "":
                    self.console.print("[bold blue] 🚨\tstderr:")
                    self.console.print(f"[red]{results['stderr']}")

                special_keys = [
                    "__pre_hook",
                    "__sync_hook",
                    "__post_hook",
                    "__total_python_runtime_seconds",
                    "__qpu_execution_time_seconds",
                    "__fridge_info",
                ]
                special_data = {}
                for k in special_keys:
                    if k in results["result"].keys():
                        special_data[k] = results["result"][k]
                        results["result"].pop(k)
                if results["result"] != {}:
                    self.console.print("[bold blue] ⚛️ \tresult")
                    json_text = format_json_dense_arrays(
                        _truncate_strings(results["result"]), max_items=10
                    )
                    if len(json_text) > 4:
                        self.console.print(json_text[2:-2])
                    else:
                        self.console.print(json_text)
                if "__pre_hook" in special_data.keys():
                    self.console.print("[bold blue] 📎 \tpre-hook stdout:")
                    self.console.print(
                        f"{special_data['__pre_hook']['stdout']}"
                    )
                    if special_data["__pre_hook"]["stderr"] != "":
                        self.console.print("[bold blue] 📎 \tpre-hook stderr:")
                        self.console.print(
                            f"[red]{special_data['__pre_hook']['stderr']}"
                        )

                if "__sync_hook" in special_data.keys():
                    self.console.print("[bold blue] 🚀 \tsync-hook stdout:")
                    self.console.print(
                        f"{special_data['__sync_hook']['stdout']}"
                    )
                    if special_data["__sync_hook"]["stderr"] != "":
                        self.console.print("[bold blue] 🚀 \tsync-hook stderr:")
                        self.console.print(
                            f"[red]{special_data['__sync_hook']['stderr']}"
                        )

                if "__post_hook" in special_data.keys():
                    self.console.print("[bold blue] 🏁 \tpost-hook stdout:")
                    self.console.print(
                        f"{special_data['__post_hook']['stdout']}"
                    )
                    if special_data["__post_hook"]["stderr"] != "":
                        self.console.print("[bold blue] 🏁 \tpost-hook stderr:")
                        self.console.print(
                            f"[red]{special_data['__post_hook']['stderr']}"
                        )
                if "__total_python_runtime_seconds" in special_data.keys():
                    self.console.print(
                        "[bold blue] 🕗 🐍 \ttotal Python execution time (s)"
                    )
                    self.console.print(
                        "%.3f" % special_data["__total_python_runtime_seconds"]
                    )
                if "__qpu_execution_time_seconds" in special_data.keys():
                    self.console.print(
                        "[bold blue] 🕗 ⚛️ \tQUA execution time (s)"
                    )
                    self.console.print(
                        "%.3f" % special_data["__qpu_execution_time_seconds"]
                    )
                if "__fridge_info" in special_data.keys():
                    self.console.print(
                        "[bold blue] :snowflake: :snowman: \tFridge info"
                    )
                    for k in special_data["__fridge_info"].keys():
                        self.console.print(
                            f"[bold blue]{k}[/bold blue] temperature = {special_data['__fridge_info'][k]['temperature_kelvin']} K measured {arrow.get(special_data['__fridge_info'][k]['unix_timestamp']).humanize()}"
                        )

                for key, value in special_data.items():
                    results["result"][key] = value
            else:
                print_json(data=_truncate_strings(results))
        if timed_out is not None:
            raise TimeoutError(timed_out)
        return results

    def _available_on_demand(self):
        if self._summary is None:
            self.console.print(
                "This backend does not expose any additional information or on-demand workflows"
            )
            return
        table = Table(title="Available on-demand workflows")
        table.add_column("workflow", justify="left", style="blue", no_wrap=True)
        table.add_column("description")
        for key, value in self._summary["ondemand"].items():
            table.add_row(f"[bold]{key}[/bold]", value["description"])
        self.console.print(table)
        self.console.print(
            ':point_right: Obtain more information about [bold]payload[/bold] specification for each workflow as\n[bold]<backand_client>.run("[blue]<workflow>[/blue]")'
        )
        self.console.print(
            ':point_right: Run on-demand workflow as \n[bold]<backand_client>.run("[blue]<workflow>[/blue]", payload[/bold])'
            ""
        )

    def summary(self) -> dict:
        """Prints on standard output human-readable information on the backend

        Returns:
            dict: backend information
        """

        if self._summary is None:
            self.console.print(
                "This backend does not expose any additional information or on-demand workflows"
            )
            return

        status = "Status:\t\t [bold green]:green_circle: online[/bold green]"
        if not self._summary["online"]:
            status = "Status:\t\t [bold red]:red_circle: offline[/bold red]"
        self.console.print(f"Backend:\t [bold blue]{self.backend}[/bold blue]")
        self.console.print(status)
        self.console.print(f"Description:\t {self._summary['description']}\n")

        table = Table(title="Available state information")
        table.add_column("datatype", justify="left", style="blue", no_wrap=True)
        table.add_column("description")
        for key, value in self._summary["state"].items():
            table.add_row(f"[bold]{key}[/bold]", value["description"])
        self.console.print(table)
        self.console.print(
            ':point_right: Get latest data as \n[bold] <backand_client>.state.get_latest("[blue]<datatype>[/blue]").data'
        )
        if "state" in self._summary["state"]:
            t = self.state.get_latest("state").timestamp
            self.console.print(
                ":point_right: Latest calibration (state): "
                + arrow.get(t).humanize()
                + f" ({t})\n"
            )

        self._available_on_demand()

        if "transpiler_target" in self._summary["state"]:
            self._summary["transpiler_target"] = self.state.get_latest(
                "transpiler_target"
            ).data
            t = self._summary["transpiler_target"]

            table = Table(title="Supported native gates")

            table.add_column(
                "Gate", justify="right", style="cyan", no_wrap=True
            )
            table.add_column("Qubits", style="magenta")
            table.add_column("Error", justify="left", style="green")
            table.add_column("Duration", justify="left", style="green")

            for key, value in t.items():
                if key == "characterization":
                    break
                qubits = []
                errors = []
                durations = []
                for v in value:
                    qubits.append(v[0])
                    if "error" in v[1].keys() and v[1]["error"] is not None:
                        errors.append(round(v[1]["error"], 4))
                    else:
                        errors.append(None)
                    if "duration" in v[1].keys():
                        durations.append(v[1]["duration"])
                    else:
                        durations.append(None)

                table.add_row(
                    f"[bold]{key}[/bold]",
                    str(qubits)[1:-1],
                    str(errors)[1:-1],
                    str(durations)[1:-1],
                )
            self.console.print(table)

        if self._summary["runtime"]["visa"] != {}:
            table = Table(title="Runtime available VISA instruments")

            table.add_column(
                "instrument", justify="left", style="cyan", no_wrap=True
            )
            table.add_column("description")

            for key, value in self._summary["runtime"]["visa"].items():
                table.add_row(f"[bold]{key}[/bold]", value["description"])

            self.console.print(table)
            self.console.print(
                ':point_right: Use in pre-, post- or sync- hook as \nfrom iqcc_cloud_client.runtime import get_visa_client\nx = get_visa_client("[bold blue]<instrument>[/bold blue]")'
            )

        return self._summary

    @property
    def state(
        self, state_service_url="https://state.i-qcc.com"
    ) -> StateService:
        """Service providing state information

        Args:
            state_service_url (str, optional): URL of the state service. Defaults to "https://state.i-qcc.com".

        Returns:
            StateService: Provides state of the backends
        """
        return StateService(
            url=state_service_url, backend=self.backend, headers=self.headers
        )

    @property
    def data(self) -> StateService:
        """Service providing data access. Requires that `datastore` is set
        initializing backend client.

        Returns:
            StateService: Stores, provides and queries data for the project.
        """
        if self.data_store_project is None or self.data_store_url is None:
            raise ValueError(
                "Define data_store when initializing backend to use this method."
            )
        headers = self.headers.copy()
        headers["iqcc-datastore-project"] = self.data_store_project
        return StateService(
            url=self.data_store_url, backend=self.backend, headers=headers
        )
