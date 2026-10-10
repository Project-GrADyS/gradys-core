"""Lifecycle events provided by the environment."""

from typing import ClassVar

from gradys_core.primitives import BaseEvent, EventId, environment_event


@environment_event
class SimulationInitializationEvent(BaseEvent):
    """Notify a protocol that its environment lifecycle has begun.

    The environment decides when to deliver this event; injecting a connection
    does not emit it automatically. The event carries no payload.
    """

    event_id: ClassVar[EventId] = "SimulationInitializationEvent"
    """Identifier for the simulation initialization event kind."""
