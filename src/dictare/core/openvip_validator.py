"""OpenVIP v1.0 message validation using compiled JSON Schema.

Schema is compiled once at import time. Validation is fast (~μs per call)
because fastjsonschema generates native Python code from the schema.
"""

from __future__ import annotations

import json
from pathlib import Path

import fastjsonschema

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "resources" / "openvip-message-v1.0.json"
_schema = json.loads(_SCHEMA_PATH.read_text())

# fastjsonschema supports up to draft-07. Convert 2020-12 keywords:
# dependentRequired → dependencies (equivalent for array-form dependencies)
if "dependentRequired" in _schema:
    _schema["dependencies"] = _schema.pop("dependentRequired")

# Register format checkers for formats used in the OpenVIP schema.
# fastjsonschema doesn't include 'uuid' by default.
_FORMATS = {
    "uuid": r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
    "date-time": r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}",
}
_validate = fastjsonschema.compile(_schema, formats=_FORMATS)

class OpenVIPValidationError(Exception):
    """Raised when a message does not conform to OpenVIP v1.0 schema."""

def validate_message(body: dict) -> None:
    """Validate *body* against the OpenVIP v1.0 message schema.

    Raises ``OpenVIPValidationError`` with a human-readable message on failure.
    """
    try:
        _validate(body)
    except fastjsonschema.JsonSchemaValueException as exc:
        raise OpenVIPValidationError(
            f"Not OpenVIP v1.0 compliant: {exc.message}"
        ) from None
