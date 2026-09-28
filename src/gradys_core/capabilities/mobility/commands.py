"""Mobility requests sent from a protocol to an environment."""

from dataclasses import dataclass
from typing import ClassVar

from gradys_core.command import BaseCommand, CommandId


@dataclass(frozen=True, slots=True)
class GotoCoords(BaseCommand):
    """Request movement to the given Cartesian coordinates."""

    command_id: ClassVar[CommandId] = "GotoCoords"
    x: float
    y: float
    z: float
