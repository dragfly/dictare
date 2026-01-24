"""Output modules for voxtype (webhooks, SSE, etc.)."""

from voxtype.output.webhook import WebhookSender
from voxtype.output.sse import SSEServer

__all__ = ["WebhookSender", "SSEServer"]
