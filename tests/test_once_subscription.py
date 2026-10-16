from collections.abc import Callable
from typing import cast

import pytest

from gradys_core.connection import Connection
from gradys_core.connection.subscriber import SubscriptionOptions
from gradys_core.primitives import BaseCommand, BaseEvent, EventHandler


class Notice(BaseEvent):
    event_id = "notice"


class EventEnvironment:
    def __init__(self, immediate: bool) -> None:
        self.immediate = immediate
        self.handlers: list[EventHandler[BaseEvent]] = []
        self.removals = 0

    async def send_command(self, command: BaseCommand) -> None:
        pass

    def check_command(self, command_type: type[BaseCommand]) -> bool:
        return True

    def check_event(self, event_type: type[BaseEvent]) -> bool:
        return True

    def subscribe_to_event[E: BaseEvent](
        self, event_type: type[E], handler: EventHandler[E]
    ) -> Callable[[], None]:
        erased = cast(EventHandler[BaseEvent], handler)
        self.handlers.append(erased)
        if self.immediate:
            self.emit()
            self.emit()

        def unsubscribe() -> None:
            self.handlers.remove(erased)
            self.removals += 1

        return unsubscribe

    def emit(self) -> None:
        for handler in tuple(self.handlers):
            handler(Notice())


@pytest.mark.parametrize("immediate", [True, False])
def test_once_cleans_up_for_both_delivery_timings(immediate: bool) -> None:
    environment = EventEnvironment(immediate)
    connection = Connection(environment)
    received: list[Notice] = []

    connection.subscribe(Notice, received.append, SubscriptionOptions(once=True))

    if immediate:
        assert environment.handlers == []
    else:
        assert len(environment.handlers) == 1

    environment.emit()
    environment.emit()

    assert len(received) == 1
    assert environment.handlers == []
    assert environment.removals == 1
