# OpenVIP Protocol Specification

Dictare implements the **OpenVIP (Open Voice Input Protocol) v1.0**.

## Official Specification

The official protocol specification is maintained at:

**https://github.com/open-voice-input/spec**

- [Protocol v1.0](https://github.com/open-voice-input/spec/blob/main/protocol/openvip-1.0.md)
- [HTTP Binding](https://github.com/open-voice-input/spec/tree/main/bindings/http)
- [Unix Socket Binding](https://github.com/open-voice-input/spec/tree/main/bindings/unix-socket)
- [JSON Schema](https://github.com/open-voice-input/spec/blob/main/schema/v1.0.json)

## Dictare Implementation

Dictare's OpenVIP implementation is in:

- `src/dictare/core/openvip.py` - Message factory
- `src/dictare/agent/socket.py` - Unix socket transport
- `src/dictare/output/sse.py` - SSE transport

### Dictare Extensions

Dictare uses these extension fields (allowed by `additionalProperties: true`):

| Field | Type | Description |
|-------|------|-------------|
| `x_submit` | boolean | Send Enter after text injection |
| `x_visual_newline` | boolean | Send Shift+Enter after text |

These are dictare-specific and may not be supported by other implementations.
