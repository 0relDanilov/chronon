"""Task API: submit, poll and revoke tasks under /task/{backend}/.

Only the health endpoint exists so far.
"""

from fastapi import FastAPI

app = FastAPI(title="chronon-api")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Report that the process is up.

    Returns:
        A fixed status document.
    """
    return {"status": "ok"}
