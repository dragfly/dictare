"""Internal event system for voxtype.

Provides a simple publish/subscribe event bus for decoupled communication
between components.

Usage:
    from voxtype.events import bus

    # Subscribe
    bus.subscribe("agents.changed", my_handler)

    # Publish
    bus.publish("agents.changed", agent_ids=["voxtype"])
"""

from voxtype.events.bus import EventBus, bus

__all__ = ["EventBus", "bus"]
