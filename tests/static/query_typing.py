"""Type-check only: preserve both the concrete query and its response."""

from typing import assert_type

from gradys_core.primitives import BaseCommand, BaseEvent, BaseQuery
from gradys_core.protocol import ProtocolContext
from gradys_core.protocol.handles import QueryHandle


class PositionResponse(BaseEvent):
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


async def check_query_types(context: ProtocolContext) -> None:
    position = context.require_query(GetPosition)
    assert_type(position, QueryHandle[GetPosition, PositionResponse])
    assert_type(GetPosition.query_types(), tuple[type[GetPosition], type[PositionResponse]])
    assert_type(await position.request(GetPosition(1)), PositionResponse)
    await position.request(OtherQuery())  # type: ignore[arg-type]
    context.require_query(BaseCommand)  # type: ignore[arg-type]
