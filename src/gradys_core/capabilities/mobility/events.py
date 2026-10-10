"""Mobility observations published by an environment."""

from typing import ClassVar

from gradys_core.primitives import BaseEvent, EventId, environment_event


@environment_event
class PositionUpdate(BaseEvent):
    """Observe a position in the same Cartesian frame as ``GotoCoords``.

    The environment defines the origin, axis orientation, and distance units.
    An update has no request identifier and does not imply that a particular
    movement command has completed.

    Attributes:
        event_id: Identifier for this position event kind.
        x: Observed coordinate along the frame's x axis.
        y: Observed coordinate along the frame's y axis.
        z: Observed coordinate along the frame's z axis.
    """

    event_id: ClassVar[EventId] = "PositionUpdate"
    x: float
    y: float
    z: float
