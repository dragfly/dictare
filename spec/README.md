# OpenVIP Protocol Specification

Voxtype implements the **OpenVIP (Open Voice Input Protocol) v1.0**.

## Official Specification

The official protocol specification is maintained at:

**https://github.com/open-voice-input/spec**

- [Protocol v1.0](https://github.com/open-voice-input/spec/blob/main/protocol/openvip-1.0.md)
- [HTTP Binding](https://github.com/open-voice-input/spec/tree/main/bindings/http)
- [Unix Socket Binding](https://github.com/open-voice-input/spec/tree/main/bindings/unix-socket)
- [JSON Schema](https://github.com/open-voice-input/spec/blob/main/schema/v1.0.json)

## Voxtype Implementation

Voxtype's OpenVIP implementation is in:

- `src/voxtype/core/openvip.py` - Message factory
- `src/voxtype/agent/socket.py` - Unix socket transport
- `src/voxtype/output/sse.py` - SSE transport

### Voxtype Extensions

Voxtype uses these extension fields (allowed by `additionalProperties: true`):

| Field | Type | Description |
|-------|------|-------------|
| `x_submit` | boolean | Send Enter after text injection |
| `x_visual_newline` | boolean | Send Shift+Enter after text |

These are voxtype-specific and may not be supported by other implementations.
