"""Await typed query responses through a synchronously configured protocol.

Run from the repository root with ``python -m showcases.queries``.
"""

import asyncio

from gradys_core.capabilities.mobility import GotoCoords, PositionUpdate
from gradys_core.protocol import BaseProtocol, ProtocolContext

from .checks import check
from .mock_environment import GetPosition, MockEnvironment


class PositionProtocol(BaseProtocol):
    """Retain movement and query handles for asynchronous use after setup."""

    def run(self, context: ProtocolContext) -> None:
        """Validate both query capabilities and retain the typed handles."""
        self.position = context.require_query(GetPosition)
        self.move = context.require_command(GotoCoords)

    async def current_position(self) -> PositionUpdate:
        """Return the response event directly from an awaited query."""
        return await self.position.request(GetPosition())


async def main() -> None:
    """Check queries before and after an awaited movement command."""
    environment = MockEnvironment()
    protocol = PositionProtocol()
    environment.bind(protocol)
    environment.start()

    initial = await protocol.current_position()
    check((initial.x, initial.y, initial.z) == (0.0, 0.0, 0.0),
          "awaited query returns the initial position")

    await protocol.move.send(GotoCoords(1.0, 2.0, 3.0))
    current = await protocol.current_position()
    check((current.x, current.y, current.z) == (1.0, 2.0, 3.0),
          "query response reflects the executed movement")
    check([type(command) for command in environment.executed] == [GetPosition, GotoCoords, GetPosition],
          "movement and query commands execute in order")


if __name__ == "__main__":
    asyncio.run(main())
