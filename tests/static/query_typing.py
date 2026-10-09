"""Type-check only: preserve both the concrete query and its response."""

from typing import assert_type

from gradys_core.primitives import BaseCommand, BaseEvent, BaseQuery
from gradys_core.protocol import BaseProtocol
from gradys_core.protocol.handles import QueryHandle


class PositionResponse(BaseEvent):
    pass


class OtherResponse(BaseEvent):
    pass


class GetPosition(BaseQuery[PositionResponse]):
    def __init__(self, node_id: int) -> None:
        self.node_id = node_id

    @classmethod
    def response_type(cls) -> type[PositionResponse]:
        return PositionResponse


class OtherQuery(BaseQuery[PositionResponse]):
    @classmethod
    def response_type(cls) -> type[PositionResponse]:
        return PositionResponse


protocol = BaseProtocol()
position = protocol.require_query(GetPosition)
assert_type(position, QueryHandle[GetPosition, PositionResponse])
assert_type(GetPosition.query_types(), tuple[type[GetPosition], type[PositionResponse]])


def on_position(response: PositionResponse) -> None:
    pass


def on_other(response: OtherResponse) -> None:
    pass


position.request(GetPosition(1), on_position)
position.request(OtherQuery(), on_position)  # type: ignore[arg-type]
position.request(GetPosition(1), on_other)  # type: ignore[arg-type]
protocol.require_query(BaseCommand)  # type: ignore[arg-type]
