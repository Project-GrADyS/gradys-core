"""Type-check the context handles and asynchronous protocol contract."""

from typing import assert_type

from gradys_core.capabilities.mobility import GotoCoords, PositionUpdate
from gradys_core.protocol import (
    BaseProtocol,
    CommandHandle,
    EventHandle,
    ProtocolContext,
)


class Example(BaseProtocol):
    async def run(self, context: ProtocolContext) -> None:
        command = context.require_command(GotoCoords)
        event = context.require_event(PositionUpdate)
        assert_type(command, CommandHandle[GotoCoords])
        assert_type(event, EventHandle[PositionUpdate])
        self.command = command
        event.subscribe(self.on_position)
        event.subscribe(self.wrong_handler)  # type: ignore[arg-type]

    async def move(self) -> None:
        assert_type(await self.command.send(GotoCoords(1.0, 2.0, 3.0)), None)
        await self.command.send(PositionUpdate)  # type: ignore[arg-type]

    def on_position(self, event: PositionUpdate) -> None:
        pass

    def wrong_handler(self, event: GotoCoords) -> None:
        pass


class SyncExample(BaseProtocol):
    def run(self, context: ProtocolContext) -> None:  # type: ignore[override]
        pass
