"""Output modules for voxtype (webhooks, SSE, etc.)."""

from voxtype.output.sse import SSEServer
from voxtype.output.webhook import WebhookSender

__all__ = ["WebhookSender", "SSEServer"]
