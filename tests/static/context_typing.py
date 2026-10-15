"""Type-check the context handles and synchronous protocol contract."""

from typing import assert_type

from gradys_core.capabilities.mobility import GotoCoords, PositionUpdate
from gradys_core.protocol import (
    BaseProtocol,
    CommandHandle,
    EventHandle,
    ProtocolContext,
)


class Example(BaseProtocol):
    def run(self, context: ProtocolContext) -> None:
        command = context.require_command(GotoCoords)
        event = context.require_event(PositionUpdate)
        assert_type(command, CommandHandle[GotoCoords])
        assert_type(event, EventHandle[PositionUpdate])
        command.send(GotoCoords(1.0, 2.0, 3.0))
        event.subscribe(self.on_position)
        command.send(PositionUpdate)  # type: ignore[arg-type]
        event.subscribe(self.wrong_handler)  # type: ignore[arg-type]

    def on_position(self, event: PositionUpdate) -> None:
        pass

    def wrong_handler(self, event: GotoCoords) -> None:
        pass


class AsyncExample(BaseProtocol):
    async def run(self, context: ProtocolContext) -> None:  # type: ignore[override]
        pass
