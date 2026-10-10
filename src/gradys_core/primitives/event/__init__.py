"""Shared event types and event definition helpers."""

from .decorator import (
    environment_event,
    is_environment_event,
    validate_environment_event,
)
from .event import BaseEvent, EventHandler, EventId

__all__ = [
    "BaseEvent",
    "EventHandler",
    "EventId",
    "environment_event",
    "is_environment_event",
    "validate_environment_event",
]
