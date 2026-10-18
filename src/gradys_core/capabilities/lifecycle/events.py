"""Lifecycle events provided by the environment."""

from dataclasses import dataclass
from typing import ClassVar

from gradys_core.primitives import BaseEvent, EventId


@dataclass(frozen=True, slots=True)
class SimulationInitializationEvent(BaseEvent):
    """Notify a protocol that its environment lifecycle has begun.

    The environment decides when to deliver this event; creating a connection
    does not emit it automatically. The event carries no payload.
    """

    event_id: ClassVar[EventId] = "SimulationInitializationEvent"
    """Identifier for the simulation initialization event kind."""
