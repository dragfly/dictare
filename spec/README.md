# OpenVIP Protocol Specification

Dictare implements the **OpenVIP (Open Voice Input Protocol) v1.0**.

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

### Dictare Extensions

Dictare uses these extension fields (allowed by `additionalProperties: true`):

| Field | Type | Description |
|-------|------|-------------|
| `x_submit` | boolean | Agent should submit (send Enter) after the transcription |
| `x_visual_newline` | boolean | Agent should insert a visual newline (Shift+Enter) instead of submitting |

These are dictare-specific and may not be supported by other implementations.
