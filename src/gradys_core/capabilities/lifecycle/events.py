"""Lifecycle events provided by the environment."""

from typing import ClassVar

from gradys_core.primitives import BaseEvent, EventId, environment_event


@environment_event
class SimulationInitializationEvent(BaseEvent):
    """The environment has begun this protocol's simulation lifecycle."""

    event_id: ClassVar[EventId] = "SimulationInitializationEvent"
