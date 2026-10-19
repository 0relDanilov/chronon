"""Pieces shared by the API and state services: JSON errors and auth.

Every error leaves as ``{"detail": "<readable>"}``. The client calls
``r.json()["detail"]`` on errors, in the state service without a ``try``
(state.py:94-95), so a non-JSON 500 would crash its constructor.
"""

import logging
import uuid
from functools import cache
from typing import Annotated, Any

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from chronon import auth
from chronon.settings import get_settings

log = logging.getLogger("chronon")


def install_json_errors(app: FastAPI) -> None:
    """Make every error response JSON ``{"detail": str}``.

    Args:
        app: The application to configure.
    """

    @app.exception_handler(StarletteHTTPException)
    async def http_error(  # pyright: ignore[reportUnusedFunction]
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse({"detail": str(exc.detail)}, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(  # pyright: ignore[reportUnusedFunction]
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        parts: list[str] = []
        for err in exc.errors():
            where = ".".join(str(p) for p in err.get("loc", ()))
            parts.append(f"{where}: {err.get('msg', 'invalid')}")
        return JSONResponse(
            {"detail": "Invalid request: " + "; ".join(parts)}, 422
        )

    @app.exception_handler(auth.AuthError)
    async def auth_error(  # pyright: ignore[reportUnusedFunction]
        request: Request, exc: auth.AuthError
    ) -> JSONResponse:
        return JSONResponse({"detail": exc.detail}, exc.status)

    @app.exception_handler(Exception)
    async def unhandled(  # pyright: ignore[reportUnusedFunction]
        request: Request, exc: Exception
    ) -> JSONResponse:
        ref = uuid.uuid4().hex[:8]
        log.exception("unhandled error ref=%s", ref)
        return JSONResponse(
            {
                "detail": f"Internal error (ref {ref}): "
                f"{type(exc).__name__}. The operators can find it in the "
                f"service log by this ref."
            },
            500,
        )


@cache
def provider_keys() -> dict[str, list[Any]]:
    """Load provider public keys once per process.

    Returns:
        Keys per backend.
    """
    return auth.load_keys(get_settings().provider_keys_dir)


def principal(
    backend: str, authorization: Annotated[str | None, Header()] = None
) -> auth.Principal:
    """FastAPI dependency: the verified caller for ``backend``.

    Args:
        backend: From the path.
        authorization: The ``Authorization`` header.

    Returns:
        The verified principal.
    """
    return auth.verify(auth.bearer(authorization), backend, provider_keys())
