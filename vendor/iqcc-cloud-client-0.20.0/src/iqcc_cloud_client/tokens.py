from datetime import datetime
from typing import List

import jwt
import toml
from rich.console import Console

from iqcc_cloud_client.cli import get_config_file


class TokenGenerator(object):
    def __init__(self, backend_name):
        """Provider utility to generate tokens for users of their backends."""
        self._console = Console()
        with open(get_config_file(), "r") as f:
            data = toml.load(f)
        if "provider_private_keys" not in data.keys():
            self._console.print(
                "[red bold]You don't have registered provider private key. Please run first:[/red bold]"
            )
            self._console.print("[blue bold]iqcc-cloud provider[/blue bold]")
            exit()
        elif backend_name not in data["provider_private_keys"].keys():
            self._console.print(
                f"Cannot find provider private key for [blue bold]{backend_name}[/blue bold]"
            )
            self._console.print(
                "Existing keys = " + str(data["provider_private_keys"].keys())
            )
            exit()
        self.private_key = data["provider_private_keys"][backend_name]
        self.backend_name = backend_name

    def time_window(
        self,
        user_uid: str,
        time_start: float,
        time_end: float,
        roles: List = [],
        projects: List = [],
    ):
        """Generate token that gives user access to backend in certain time window.

        Args:
            user_uid (str): string unique identifier of the user
            time_start (float): Starting time in seconds since Unix epoch.
            time_stop (_type_): Ending time of time windows in seconds since Unix epoch.
            roles (list): List of special roles, like 'calibrator'. Optional, default [].
            projects (list): List of project it has access to for data storage and query. Optional, default []

        Returns:
            _type_: encoded user access token
        """
        payload = {
            "user_id": user_uid,
            "qpu": {
                self.backend_name: {
                    "from": time_start,
                    "to": time_end,
                    "access": roles,
                    "project": projects,
                }
            },
            "expires": time_end,
        }

        encoded = jwt.encode(payload, self.private_key, algorithm="RS256")
        self._console.print(
            f"Generated token gives access to user [bold blue]{user_uid}[/bold blue] to backend [bold blue]{self.backend_name}[/bold blue] starting from {datetime.fromtimestamp(time_start)} until {datetime.fromtimestamp(time_end)}"
        )
        return encoded

    def pay_as_you_go(self):
        print("Not yet available")
        pass

    def allowed_total_time(self):
        print("Not yet available")
        pass

    def invalidate(self):
        print("Not yet available")
        pass

    def list_tokens(self):
        print("Not yet available")
        pass
