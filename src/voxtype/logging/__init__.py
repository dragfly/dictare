"""Structured logging module for voxtype.

Idiomatic Python logging approach:
    # At app startup:
    from voxtype.logging import setup_logging
    setup_logging(log_path="...", level=logging.INFO)

    # In any module:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("event_name", extra={"key": "value"})
"""

# New idiomatic API
# Legacy API (deprecated, for backward compatibility)
from voxtype.logging.jsonl import (
    JSONLLogger,
    LogLevel,
)
from voxtype.logging.setup import (
    DEFAULT_LOG_DIR,
    get_default_log_path,
    setup_logging,
    shutdown_logging,
)

__all__ = [
    # New API
    "setup_logging",
    "shutdown_logging",
    "DEFAULT_LOG_DIR",
    "get_default_log_path",
    # Legacy (deprecated)
    "JSONLLogger",
    "LogLevel",
]
