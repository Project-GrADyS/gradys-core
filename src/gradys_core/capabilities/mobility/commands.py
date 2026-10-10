"""Mobility requests sent from a protocol to an environment."""

from dataclasses import dataclass
from typing import ClassVar

from gradys_core.primitives import BaseCommand, CommandId


@dataclass(frozen=True, slots=True)
class GotoCoords(BaseCommand):
    """Request movement to a destination in the environment's Cartesian frame.

    The environment defines the origin, axis orientation, and distance units;
    they must agree with those used by ``PositionUpdate``. Sending this command
    does not itself confirm arrival.

    Attributes:
        command_id: Identifier for this movement command kind.
        x: Destination coordinate along the frame's x axis.
        y: Destination coordinate along the frame's y axis.
        z: Destination coordinate along the frame's z axis.
    """

    command_id: ClassVar[CommandId] = "GotoCoords"
    x: float
    y: float
    z: float
