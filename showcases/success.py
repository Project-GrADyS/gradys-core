"""Async execution with awaited commands, events, and later requirements.

Run from the repository root with ``python -m showcases.success``.
"""

import asyncio

from gradys_core.capabilities.lifecycle import SimulationInitializationEvent
from gradys_core.capabilities.mobility import GotoCoords, PositionUpdate
from gradys_core.protocol import BaseProtocol, ProtocolContext

from .checks import check
from .mock_environment import MockEnvironment


class MoveProtocol(BaseProtocol):
    """Set up movement during start and record lifecycle/position events.

    Attributes:
        notifications: Event descriptions in delivery order.
        move: Sending handle for this protocol's movement requirement.
    """

    def __init__(self, destination: tuple[float, float, float]) -> None:
        """Store configuration and initialize local state."""
        self.destination = destination
        self.notifications: list[str] = []

    async def start(self, context: ProtocolContext) -> None:
        """Subscribe to events, retain a handle, and await the initial command."""
        context.require_event(SimulationInitializationEvent).subscribe(self.on_start)
        context.require_event(PositionUpdate).subscribe(self.on_position)
        self.move = context.require_command(GotoCoords)
        await self.move_to_destination()

    async def move_to_destination(self) -> None:
        """Await acceptance of the configured movement command."""
        await self.move.send(GotoCoords(*self.destination))

    def on_start(self, event: SimulationInitializationEvent) -> None:
        """Record the environment's initialization notification."""
        self.notifications.append("started")

    def on_position(self, event: PositionUpdate) -> None:
        """Record a delivered position as a readable coordinate triple."""
        self.notifications.append(f"position: ({event.x}, {event.y}, {event.z})")


async def main() -> None:
    """Check startup operations and handles used after start returns."""
    print("Run: context requirements, events and commands")
    environment = MockEnvironment()
    protocol = MoveProtocol((1.0, 2.0, 3.0))

    context = await environment.bind(protocol)
    check(environment.executed == [], "commands wait until start")
    environment.start()
    check(protocol.notifications == ["started", "position: (1.0, 2.0, 3.0)"],
          "start delivers lifecycle and position events")

    later_move = context.require_command(GotoCoords)
    await later_move.send(GotoCoords(4.0, 5.0, 6.0))
    check(protocol.notifications[-1] == "position: (4.0, 5.0, 6.0)", "requirement after binding works")
    check(len(environment.executed) == 2, "every command executes")


if __name__ == "__main__":
    asyncio.run(main())
