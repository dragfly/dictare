"""Command schema definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ParamType(Enum):
    """Parameter types for command arguments."""

    STRING = "string"
    INT = "integer"
    BOOL = "boolean"
    FLOAT = "number"


@dataclass
class CommandParam:
    """Definition of a command parameter."""

    name: str
    type: ParamType
    description: str = ""
    required: bool = True
    default: Any = None


@dataclass
class CommandSchema:
    """Schema definition for a command."""

    name: str
    description: str
    params: list[CommandParam] = field(default_factory=list)
    category: str = "general"

    def to_json_schema(self) -> dict:
        """Convert to JSON Schema format for LLM."""
        schema: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
        }

        if self.params:
            properties = {}
            required = []

            for param in self.params:
                properties[param.name] = {
                    "type": param.type.value,
                    "description": param.description,
                }
                if param.default is not None:
                    properties[param.name]["default"] = param.default
                if param.required:
                    required.append(param.name)

            schema["parameters"] = {
                "type": "object",
                "properties": properties,
            }
            if required:
                schema["parameters"]["required"] = required

        return schema


def schemas_to_json(schemas: list[CommandSchema]) -> list[dict]:
    """Convert list of schemas to JSON format for LLM."""
    return [s.to_json_schema() for s in schemas]
