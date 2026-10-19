import os
from pathlib import Path

import jwt
import toml
import typer
from cryptography.hazmat.backends import (
    default_backend as crypto_default_backend,
)
from cryptography.hazmat.primitives import serialization as crypto_serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from rich.console import Console
from typing_extensions import Annotated

import iqcc_cloud_client

app = typer.Typer()
console = Console()


def get_config_file():
    Path(os.path.join(os.path.expanduser("~"), ".config", "iqcc_cloud")).mkdir(
        parents=True, exist_ok=True
    )
    config_file = os.path.join(
        os.path.expanduser("~"), ".config", "iqcc_cloud", "config.toml"
    )
    Path(config_file).touch(exist_ok=True)

    return config_file


@app.command()
def setup(
    IQCC_API_token: Annotated[
        str, typer.Option(prompt="Paste your IQCC API token and press enter")
    ],
):
    """Sets up a token for usage of the IQCC for current user

    Args:
        token (str): API token provided by the IQCC
    """
    with open(get_config_file(), "r") as f:
        data = toml.load(f)
        if data == "":
            data = {}
    with open(
        get_config_file(),
        "w",
    ) as f:
        if "tokens" not in data.keys():
            data["tokens"] = {}
        try:
            decoded_data = jwt.decode(
                IQCC_API_token, options={"verify_signature": False}
            )
            for backend in decoded_data["qpu"].keys():
                data["tokens"][backend] = IQCC_API_token

            console.print(
                f":thumbs_up: Token for user [bold blue]{decoded_data['user_id']}[/bold blue] access to [bold blue]{backend}[/bold blue] provided"
            )

        except Exception as _:
            console.print("[bold red]:red_circle: Invalid JWT token passed")
            exit()
        toml.dump(data, f)

    console.print(
        "[bold green]:white_check_mark: Your access token is setup successfully.[/bold green]\n:rocket: Now you can use IQCC client without explicitly specifying the token."
    )


@app.command()
def provider(
    backend_name: Annotated[
        str, typer.Option(prompt="Enter name of backend you provide")
    ],
):
    """Generates a public and private key for backend provider

    Args:
        backend_name (str): name of backend for which you want to generate provider token
    """
    key = rsa.generate_private_key(
        backend=crypto_default_backend(), public_exponent=65537, key_size=2048
    )

    private_key = key.private_bytes(
        crypto_serialization.Encoding.PEM,
        crypto_serialization.PrivateFormat.PKCS8,
        crypto_serialization.NoEncryption(),
    )

    public_key = key.public_key().public_bytes(
        crypto_serialization.Encoding.PEM,
        crypto_serialization.PublicFormat.PKCS1,
    )

    with open(get_config_file(), "r") as f:
        data = toml.load(f)
        if data == "":
            data = {}
    if (
        "provider_private_keys" in data.keys()
        and backend_name in data["provider_private_keys"].keys()
    ):
        if not typer.confirm(
            f"""You already have key registered for backend {backend_name}\nAre you sure you want to overwrite it?"""
        ):
            console.print(
                "Aborting creation of new backend key, since there is existing one."
            )
            return
    with open(
        get_config_file(),
        "w",
    ) as f:
        if "provider_private_keys" not in data.keys():
            data["provider_private_keys"] = {}

        data["provider_private_keys"][backend_name] = private_key.decode(
            "utf-8"
        )
        toml.dump(data, f)
    console.line()
    console.print(
        f":thumbs_up: Provider private key for backend [bold blue]{backend_name}[/bold blue] generated. [bold green]Please share the following public key with cloud server provider.[/bold green]"
    )
    console.line()
    console.rule(
        f"[bold green]Public key for cloud server [/bold green][bold blue]{backend_name}[/bold blue]"
    )
    print(public_key.decode("utf-8"))
    console.rule()
    console.line()
    console.print(
        ":rocket: Once the cloud server has this key set for your backend, you will be able to issue tokens to your users using iqcc_cloud.tokens functions"
    )


@app.command()
def version():
    """Prints version information"""
    print(f"iqcc-cloud-client version {iqcc_cloud_client.__version__}")


if __name__ == "__main__":
    app()
