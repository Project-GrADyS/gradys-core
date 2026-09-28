"""Mobility observations published by an environment."""

from typing import ClassVar

from gradys_core.event import BaseEvent, EventId, environment_event


@environment_event
class PositionUpdate(BaseEvent):
    """A position observation in the same Cartesian frame as ``GotoCoords``."""

    event_id: ClassVar[EventId] = "PositionUpdate"
    x: float
    y: float
    z: float
