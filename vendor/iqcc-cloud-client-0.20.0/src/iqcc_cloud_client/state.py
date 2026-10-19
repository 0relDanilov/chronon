from typing import List, Union

import arrow
import httpx
import plotext as plt
from deepdiff import DeepDiff, extract
from pydantic import JsonValue
from rich import print_json
from rich.console import Console
from rich.table import Table

from iqcc_cloud_client.interfaces import Dataset, DatasetMeta


class StateService(object):
    def __init__(self, url: str, backend: str, headers: dict):
        """State service

        Args:
            url (str): state service URL
            backend (str): backend we are working with
            headers (dict): authentication token and similar
        """
        self.url = url
        self.backend = backend
        self.headers = headers
        self.console = Console()
        self.timeout = 60
        self.client = httpx.Client(
            headers=self.headers, timeout=self.timeout, http2=True, http1=False
        )

    def list(
        self,
        datatype: str | None = None,
        producer: str | None = None,
        skip: int = 0,
        limit: int = 10,
        terminal_output=False,
    ) -> List[DatasetMeta]:
        """List all data for the backend. Returns newest data first.

        Args:
            datatype (str | None, optional): Filter by data type for backend (e.g. quam_state). Defaults to None.
            producer (str | None, optional): Filter by username of the user who produced the data. Defaults to None.
            skip (int, optional): Skip first N items. Defaults to 0.
            limit (int, optional): Limit maximal number of returned items. Defaults to 10.
            terminal_output (bool, optional): Write results to terminal. Defaults to False.

        Returns:
            List[DatasetMeta]: _description_
        """
        payload = {
            "skip": skip,
            "limit": limit,
        }
        if datatype is not None:
            payload["datatype"] = datatype
        if producer is not None:
            payload["producer"] = producer
        r = self.client.get(
            self.url + f"/{self.backend}/state/",
            params=payload,
        )
        if r.status_code == httpx.codes.OK:
            if terminal_output:
                if datatype is not None:
                    table = Table(
                        title=f"{datatype} for backend {self.backend}"
                    )
                else:
                    table = Table(
                        title=f"All data for backend [bold blue]{self.backend}[/bold blue]"
                    )
                table.add_column(
                    "id", justify="right", style="cyan", no_wrap=True
                )
                table.add_column("type", style="cyan", justify="left")
                table.add_column("comment")
                table.add_column("producer", justify="right")
                table.add_column("time", justify="right")

                for v in r.json():
                    table.add_row(
                        str(v["id"]),
                        v["type"],
                        v["comment"],
                        v["producer"],
                        arrow.get(v["timestamp"]).humanize(),
                    )
                self.console.print(table)
            return [DatasetMeta(**v) for v in r.json()]
        else:
            self.console.print(f"[bold red]🚨 Error code {r.status_code}")
            self.console.print(f"[bold red]{r.json()['detail']}")

    def push(
        self,
        datatype: str,
        data: JsonValue = "",
        comment: str = "",
        parent_id: int = None,
    ) -> Dataset:
        """Submit new dataset for a given backend. Restricted only to users that
        have `calibrator` access to the backend.

        Args:
            datatype (str): dataset type, used for filtering datasets (e.g. `quam_data`)
            data (dict, optional): Any valid JSON dict. Defaults to "".
            comment (str, optional): Short human-readable comment about this data. Defaults to "".
            parent_id (int, optional): If this dataset is considered to be linked to another parent dataset, provide original parent dataset ID. Note that both datasets have to correspond to the same backend. Defaults to None.

        Returns:
            Dataset: _description_
        """
        payload = {
            "type": datatype,
            "data": data,
            "comment": comment,
            "parent_id": parent_id,
        }
        r = self.client.post(
            self.url + f"/{self.backend}/state/",
            json=payload,
        )
        if r.status_code == httpx.codes.OK:
            return Dataset(**r.json())
        else:
            self.console.print(f"[bold red]🚨 Error code {r.status_code}")
            self.console.print(f"[bold red]{r.json()['detail']}")
        pass

    def get(self, dataset_id: int, terminal_output=False) -> Dataset:
        """Get requested dataset ID.

        Args:
            dataset_id (int): ID of requested dataset
            terminal_output (bool, optional): Pretty print output in terminal.. Defaults to False.

        Returns:
            Dataset: _description_
        """
        r = self.client.get(
            self.url + f"/{self.backend}/state/{dataset_id}",
        )
        if r.status_code == httpx.codes.OK:
            if terminal_output:
                print_json(data=r.json())
            if r.json()["backend"] != self.backend:
                self.console.print(
                    f"[bold red]WARNING: Requested dataset ID does not correspond to backend {self.backend}."
                )
            return Dataset(**r.json())
        else:
            self.console.print(f"[bold red]🚨 Error code {r.status_code}")
            self.console.print(f"[bold red]{r.json()['detail']}")

    def trend(
        self,
        jsonpath: str,
        skip: int = 0,
        limit: int = 10,
        datatype: str | None = None,
        producer: str | None = None,
        terminal_output=False,
    ) -> List[dict]:
        """Timeseries trend of data values for given jsonpath across time series.
        Starts with the newest value first.

        Args:
            jsonpath (str): Valid JSON path (e.g. `$.qubits[*].t1` or `$.qubits[2].t1`)
            skip (int, optional): Skip latest `skip` values. Defaults to 0.
            limit (int, optional): Limit how many values to retrieve. Defaults to 10.
            datatype (str | None, optional): Filter by datatype (e.g. `quam_state`). Defaults to None.
            producer (str | None, optional): Filter by username of the user who produced the data. Defaults to None.
            terminal_output (bool, optional): Pretty print output in terminal. Defaults to False.

        Returns:
            List[dict]: each element in list has `id` of dataset, `t` timestamp of data, and `value` of the requested JSON path
        """
        payload = {
            "jsonpath": jsonpath,
            "skip": skip,
            "limit": limit,
        }
        if datatype is not None:
            payload["datatype"] = datatype
        if producer is not None:
            payload["producer"] = producer
        r = self.client.get(
            self.url + f"/{self.backend}/timeseries/",
            params=payload,
        )
        if r.status_code == httpx.codes.OK:
            if terminal_output:
                times = []
                values = []
                for v in r.json():
                    if type(v["value"]) in [int, float]:
                        values.append(v["value"])
                        times.append(
                            arrow.get(v["t"]).format("YYYY-MM-DD HH:mm:ss")
                        )
                if len(values) > 0:
                    plt.date_form("Y-m-d H:M:S")
                    plt.plot(times, values)
                    plt.show()
                else:
                    self.console.print(
                        "Time series return type not int or float. Suppressing terminal plot"
                    )
            return r.json()
        else:
            self.console.print(f"[bold red]🚨 Error code {r.status_code}")
            self.console.print(f"[bold red]{r.json()['detail']}")

    def get_latest(
        self, datatype: str, producer: str = None, terminal_output=False
    ) -> Union[Dataset, None]:
        """Gets latest dataset of given datatype

        Args:
            datatype (str): data type of a requested dataset (e.g. quam_state)
            producer (str | None, optional): Filter by username of the user who produced the data. Defaults to None.
            terminal_output (bool, optional): show pretty printed terminal output. Defaults to False.

        Returns:
            Dataset: _description_
        """
        data_list = self.list(datatype, producer=producer, limit=1)
        if data_list is None or len(data_list) == 0:
            return None
        return self.get(data_list[0].id, terminal_output=terminal_output)

    def diff(self, old_data_id: int, new_data_id: int):
        """Compares two datasets and prints difference in human readable manner in terminal

        Args:
            old_data_id (int): ID of initial dataset
            new_data_id (int): ID of new dataset
        """
        a = self.get(old_data_id).model_dump()
        b = self.get(new_data_id).model_dump()
        diff = DeepDiff(a["data"], b["data"], ignore_order=True)
        table = Table()

        table.add_column("Comparing", style="cyan", no_wrap=True)
        table.add_column(f"[bold]data_id={old_data_id}[/bold]")
        table.add_column(f"[bold]data_id={new_data_id}[/bold]")

        table.add_row("Backend", a["backend"], b["backend"])
        table.add_row("Datatype", a["type"], b["type"])
        table.add_row("Comment", a["comment"], b["comment"])
        table.add_row("Producer", a["producer"], b["producer"])
        table.add_row(
            "Timestamp",
            arrow.get(a["timestamp"]).humanize(),
            arrow.get(b["timestamp"]).humanize(),
        )

        console = Console()
        console.print(table)
        if "values_changed" in diff.keys():
            self.console.print("\n[bold blue] ~ UPDATED VALUES[/bold blue]")
            for key, value in diff["values_changed"].items():
                self.console.print(
                    f"[bold blue]data{key[4:]}[/bold blue] {value['old_value']} -> {value['new_value']}"
                )
        if "dictionary_item_added" in diff.keys():
            self.console.print("\n[bold green] + ADDED KEYS[/bold green]")
            for items in diff["dictionary_item_added"]:
                self.console.print(
                    f"[bold green]data{items[4:]}[/bold green]\t\t-> {extract(b['data'], items)}"
                )

        if "dictionary_item_removed" in diff.keys():
            self.console.print("\n[bold red] - REMOVED KEYS[/bold red]")
            for items in diff["dictionary_item_removed"]:
                self.console.print(
                    f"[bold red]data{items[4:]}[/bold red] {extract(a['data'], items)} ->"
                )

        if "iterable_item_added" in diff.keys():
            self.console.print("\n[bold green]ADDED ARRAY VALUES[/bold green]")
            for key, value in diff["iterable_item_added"].items():
                self.console.print(
                    f"[bold green]data{key[4:]}[/bold green] \t\t -> {value}"
                )

        if "iterable_item_removed" in diff.keys():
            self.console.print("\n[bold red]REMOVED ARRAY VALUES[/bold red]")
            for key, value in diff["iterable_item_removed"].items():
                self.console.print(
                    f"[bold red]data{key[4:]}[/bold red] {value} ->"
                )
        self.console.rule()

    def list_children(
        self,
        parent_dataset_id: int,
        datatype: str | None = None,
        producer: str | None = None,
        skip: int = 0,
        limit: int = 10,
        terminal_output=False,
    ) -> List[DatasetMeta]:
        """List all child dataset for given parent dataset id.

        Args:
            parent_dataset_id (int): dataset id for which we should list child datasets
            datatype (str | None, optional): Filter by data type for backend (e.g. quam_state). Defaults to None.
            producer (str | None, optional): Filter by username of the user who produced the data. Defaults to None.
            skip (int, optional): Skip first N items. Defaults to 0.
            limit (int, optional): Limit maximal number of returned items. Defaults to 10.
            terminal_output (bool, optional): Write results to terminal. Defaults to False.

        Returns:
            List[DatasetMeta]: _description_
        """
        payload = {
            "skip": skip,
            "limit": limit,
        }
        if datatype is not None:
            payload["type"] = datatype
        if producer is not None:
            payload["producer"] = producer
        r = self.client.get(
            self.url + f"/{self.backend}/state/{parent_dataset_id}/children",
            params=payload,
        )
        if r.status_code == httpx.codes.OK:
            if terminal_output:
                if datatype is not None:
                    table = Table(
                        title=f"{datatype} child datasets for parent_dataset_id {parent_dataset_id}"
                    )
                else:
                    table = Table(
                        title=f"Children of parent_dataset_id [bold blue]{parent_dataset_id}[/bold blue]"
                    )
                table.add_column(
                    "id", justify="right", style="cyan", no_wrap=True
                )
                table.add_column("type", style="cyan", justify="left")
                table.add_column("comment")
                table.add_column("producer", justify="right")
                table.add_column("time", justify="right")

                for v in r.json():
                    table.add_row(
                        str(v["id"]),
                        v["type"],
                        v["comment"],
                        v["producer"],
                        arrow.get(v["timestamp"]).humanize(),
                    )
                self.console.print(table)
            return [DatasetMeta(**v) for v in r.json()]
        else:
            self.console.print(f"[bold red]🚨 Error code {r.status_code}")
            self.console.print(f"[bold red]{r.json()['detail']}")
