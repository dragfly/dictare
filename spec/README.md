# OpenVIP Protocol Specification

Dictare implements the **OpenVIP (Open Voice Interaction Protocol) v1.0**.

## Official Specification

The official protocol specification is maintained at:

**https://github.com/openvip-dev/protocol**

- [Protocol v1.0](https://github.com/openvip-dev/protocol/blob/main/protocol/openvip-1.0.md)
- [HTTP Binding](https://github.com/openvip-dev/protocol/tree/main/bindings/http)
- [JSON Schema](https://github.com/openvip-dev/protocol/blob/main/schema/v1.0.json)

## Dictare Implementation

Dictare's OpenVIP implementation is in:

- `src/dictare/core/http_server.py` — HTTP/SSE server (FastAPI)
- `src/dictare/core/openvip_messages.py` — Message factory
- `src/dictare/core/openvip_validator.py` — Schema validation
- `src/dictare/agent/` — Agent client (openvip SDK)

### Standard Extensions Used

Dictare uses both standard extensions defined in the protocol spec:

#### `x_input` — Text input behavior

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `submit` | boolean | **yes** | Agent should submit (send Enter) after the transcription |
| `newline` | boolean | **yes** | Agent should insert a visual newline (Shift+Enter) |
| `trigger` | string | no | The voice phrase that triggered this action (e.g. `"ok, send"`) |
| `confidence` | float | no | STT confidence score for the trigger phrase |
| `source` | string | no | Generator identifier (e.g. `"dictare/input-filter"`) |

#### `x_agent_switch` — Agent routing

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `target` | string | **yes** | Identifier of the agent to switch to |
| `confidence` | float | no | Confidence score (0.0–1.0) |
| `source` | string | no | Generator identifier (e.g. `"dictare/agent-filter"`) |

These are standard protocol fields — any OpenVIP implementation can use them.
