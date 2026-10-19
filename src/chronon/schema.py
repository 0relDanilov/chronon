"""JSON Schema validation for workflow payloads, with readable errors."""

# jsonschema is only partially typed; this module is the boundary that turns
# its results into plain strings for the rest of chronon.
# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false

from typing import Any

from jsonschema.exceptions import best_match
from jsonschema.validators import validator_for


def first_error(schema: dict[str, Any], payload: Any) -> str | None:
    """Validate ``payload`` and describe the most relevant error, if any.

    Uses the validator class the schema declares (draft 2020-12 by default),
    and ``best_match`` to pick the error a person should fix first.

    Args:
        schema: A JSON Schema.
        payload: The value to validate.

    Returns:
        ``"<json path>: <message>"``, or None if the payload is valid.
    """
    cls: Any = validator_for(schema)
    error: Any = best_match(cls(schema).iter_errors(payload))
    if error is None:
        return None
    return f"{error.json_path}: {error.message}"
