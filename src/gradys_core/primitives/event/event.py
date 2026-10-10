"""Event definitions shared by protocols and environments."""

from collections.abc import Callable
from typing import ClassVar

type EventId = str
"""String identifier used by environment adapters to identify an event kind."""


class BaseEvent:
    """Base for notifications delivered by an execution environment.

    Subclasses define an ``event_id`` and their payload. Use ``environment_event``
    to generate a frozen dataclass and mark a definition for adapters that
    validate environment events. Inheriting from this base alone does neither.
    """

    event_id: ClassVar[EventId]
    """Identifier for the event kind, shared by all instances of its class."""


type EventHandler[E: BaseEvent] = Callable[[E], None]
"""Callback that consumes one event of type ``E`` and returns no result."""
