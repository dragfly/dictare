# OpenVIP Protocol Specification

**Version**: 1.0
**Status**: Draft
**Last Updated**: 2025-01-25

---

## 1. Overview

OpenVIP (Open Voice Input Protocol) is an open protocol for transmitting voice input as structured messages. It defines a transport-agnostic message format that enables voice-to-text integration across applications, devices, and platforms.

### 1.1 Design Goals

1. **Simple**: JSON messages over standard transports (SSE, HTTP, WebSocket)
2. **Extensible**: Core fields + optional extensions (`x_` prefix)
3. **Transport-agnostic**: Same message format across all transports
4. **Privacy-first**: Audio processing happens locally; only text is transmitted

### 1.2 Terminology

| Term | Definition |
|------|------------|
| **Listener** | Component that captures audio, transcribes it, and emits OpenVIP messages |
| **Receiver** | Component that receives OpenVIP messages and acts on them |
| **Transport** | Mechanism for delivering messages (SSE, HTTP POST, Unix socket) |
| **Agent** | Named endpoint that can receive messages (e.g., "claude", "cursor") |

---

## 2. Message Format

All OpenVIP messages are JSON objects with the following structure:

### 2.1 Core Fields (REQUIRED)

| Field | Type | Description |
|-------|------|-------------|
| `openvip` | string | Protocol version (e.g., "1.0") |
| `type` | string | Message type (see Section 3) |
| `id` | string | Unique message identifier (UUID v4 recommended) |
| `timestamp` | string | ISO 8601 timestamp with timezone |

### 2.2 Common Fields (OPTIONAL)

| Field | Type | Description |
|-------|------|-------------|
| `source` | string | Identifier of the message source (e.g., "voxtype/2.28.0") |
| `text` | string | Transcribed text (for `message` type) |

### 2.3 Example Message

```json
{
  "openvip": "1.0",
  "type": "message",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2025-01-25T10:30:00.000Z",
  "source": "voxtype/2.28.0",
  "text": "Hello, world"
}
```

---

## 3. Message Types

### 3.1 `message`

Contains transcribed text for injection.

**Additional fields:**

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | **REQUIRED**. The transcribed text. |

**Example:**

```json
{
  "openvip": "1.0",
  "type": "message",
  "id": "...",
  "timestamp": "...",
  "text": "The transcribed text goes here"
}
```

### 3.2 `state`

Indicates a state change in the listener.

**Additional fields:**

| Field | Type | Description |
|-------|------|-------------|
| `state` | string | **REQUIRED**. New state (e.g., "idle", "recording", "transcribing") |

**Example:**

```json
{
  "openvip": "1.0",
  "type": "state",
  "id": "...",
  "timestamp": "...",
  "state": "recording"
}
```

### 3.3 `partial`

Contains partial transcription (real-time feedback during speech).

**Additional fields:**

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | **REQUIRED**. Partial transcription. |

**Example:**

```json
{
  "openvip": "1.0",
  "type": "partial",
  "id": "...",
  "timestamp": "...",
  "text": "The transcrib..."
}
```

### 3.4 `heartbeat`

Keep-alive message for connection health monitoring.

**Additional fields:** None.

**Example:**

```json
{
  "openvip": "1.0",
  "type": "heartbeat",
  "id": "...",
  "timestamp": "..."
}
```

Receivers SHOULD send heartbeats every 30-60 seconds on persistent connections.

### 3.5 `error`

Indicates an error condition.

**Additional fields:**

| Field | Type | Description |
|-------|------|-------------|
| `error` | string | **REQUIRED**. Error message. |
| `code` | string | Error code (optional). |

**Example:**

```json
{
  "openvip": "1.0",
  "type": "error",
  "id": "...",
  "timestamp": "...",
  "error": "Transcription failed",
  "code": "STT_ERROR"
}
```

---

## 4. Extensions

Extensions allow adding functionality without breaking compatibility. Extension fields MUST be prefixed with `x_`.

### 4.1 Core Extensions

#### `x_submit`

| Field | Type | Description |
|-------|------|-------------|
| `x_submit` | boolean | If `true`, receiver should submit/send after injecting text (e.g., press Enter) |

#### `x_visual_newline`

| Field | Type | Description |
|-------|------|-------------|
| `x_visual_newline` | boolean | If `true`, receiver should add a visual newline after text (e.g., Shift+Enter) |

**Example:**

```json
{
  "openvip": "1.0",
  "type": "message",
  "id": "...",
  "timestamp": "...",
  "text": "Send this message",
  "x_submit": true
}
```

### 4.2 Semantic Extensions (Future)

Reserved for future semantic intent features:

| Field | Type | Description |
|-------|------|-------------|
| `x_intent` | object | Semantic interpretation of the message |
| `x_intent.action` | string | Identified action (e.g., "open_gate") |
| `x_intent.params` | object | Action parameters |
| `x_confidence` | number | Confidence score (0.0 to 1.0) |

---

## 5. Transport: Server-Sent Events (SSE)

SSE is the primary transport for real-time message delivery to browsers and remote clients.

### 5.1 Endpoint

```
GET /agents/{agent_name}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `agent_name` | string | Name of the agent to receive messages for |

### 5.2 Authentication

Requests MUST include a valid token. Two methods are supported:

**Query Parameter:**
```
GET /agents/claude?token=voxtype_claude_abc123...
```

**Authorization Header:**
```
GET /agents/claude
Authorization: Bearer voxtype_claude_abc123...
```

### 5.3 Response Format

Content-Type: `text/event-stream`

Each OpenVIP message is sent as an SSE event:

```
event: message
data: {"openvip":"1.0","type":"message","id":"...","timestamp":"...","text":"Hello"}

event: state
data: {"openvip":"1.0","type":"state","id":"...","timestamp":"...","state":"recording"}

event: heartbeat
data: {"openvip":"1.0","type":"heartbeat","id":"...","timestamp":"..."}
```

The `event` field corresponds to the OpenVIP message `type`.

### 5.4 Connection Lifecycle

1. Client connects to `/agents/{name}?token={token}`
2. Server validates token
3. Server sends events as they occur
4. Server sends `heartbeat` every 30-60 seconds
5. Client automatically reconnects on disconnect (SSE built-in)

### 5.5 Error Responses

| Status | Description |
|--------|-------------|
| `401 Unauthorized` | Invalid or missing token |
| `404 Not Found` | Agent not found |

---

## 6. Transport: HTTP Push

HTTP Push allows the listener to send messages to a remote endpoint.

### 6.1 Endpoint

```
POST /agents/{agent_name}
```

### 6.2 Authentication

**Authorization Header:**
```
POST /agents/myapp
Authorization: Bearer {token}
Content-Type: application/json

{"openvip":"1.0","type":"message",...}
```

### 6.3 Response

| Status | Description |
|--------|-------------|
| `200 OK` | Message accepted |
| `401 Unauthorized` | Invalid token |
| `400 Bad Request` | Invalid message format |

---

## 7. Token Format

Tokens are used for authentication. The recommended format is:

```
voxtype_{agent_name}_{random_bytes}
```

Where:
- `agent_name`: The agent this token is valid for
- `random_bytes`: At least 32 bytes of cryptographically secure random data, base64url encoded

**Example:**
```
voxtype_claude_dGhpcyBpcyBhIHNhbXBsZSB0b2tlbg
```

Tokens SHOULD be:
- Generated at listener startup
- Unique per agent
- At least 256 bits of entropy

---

## 8. CORS

For browser compatibility, SSE servers MUST support CORS:

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, OPTIONS
Access-Control-Allow-Headers: Authorization
```

---

## 9. Security Considerations

### 9.1 Transport Security

- Production deployments SHOULD use HTTPS/TLS
- Tokens SHOULD be transmitted only over encrypted connections

### 9.2 Token Security

- Tokens SHOULD NOT be logged
- Tokens SHOULD be rotated periodically
- Tokens SHOULD be stored securely

### 9.3 Message Validation

Receivers SHOULD validate:
- `openvip` version is supported
- `type` is a known message type
- Required fields are present
- `id` is unique (for deduplication)

---

## 10. Versioning

The protocol version follows semantic versioning:

- **Major**: Breaking changes to core message format
- **Minor**: New message types or extensions
- **Patch**: Clarifications, documentation

Receivers SHOULD accept messages with the same major version.

---

## Appendix A: JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "OpenVIP Message",
  "type": "object",
  "required": ["openvip", "type", "id", "timestamp"],
  "properties": {
    "openvip": {
      "type": "string",
      "pattern": "^\\d+\\.\\d+$"
    },
    "type": {
      "type": "string",
      "enum": ["message", "state", "partial", "heartbeat", "error"]
    },
    "id": {
      "type": "string",
      "format": "uuid"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    },
    "source": {
      "type": "string"
    },
    "text": {
      "type": "string"
    },
    "state": {
      "type": "string"
    },
    "error": {
      "type": "string"
    },
    "code": {
      "type": "string"
    }
  },
  "patternProperties": {
    "^x_": {}
  },
  "additionalProperties": false
}
```

---

## Appendix B: Reference Implementation

The reference implementation is available at:
- **VoxType**: https://github.com/dragfly/voxtype

---

## Appendix C: Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-01-25 | Initial specification |
