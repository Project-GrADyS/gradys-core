from collections.abc import Callable
from typing import cast

import pytest

from gradys_core.connection import Connection
from gradys_core.errors import ProtocolSetUpException
from gradys_core.primitives import BaseCommand, BaseEvent, BaseQuery, EventHandler
from gradys_core.protocol import BaseProtocol, ProtocolContext


class FirstCommand(BaseCommand):
    command_id = "first"


class SecondCommand(BaseCommand):
    command_id = "second"


class Notice(BaseEvent):
    event_id = "notice"


class GetNotice(BaseQuery[Notice]):
    command_id = "get_notice"

    @classmethod
    def response_type(cls) -> type[Notice]:
        return Notice


class RecordingEnvironment:
    def __init__(self) -> None:
        self.seen: list[tuple[str, object]] = []
        self.handlers: list[EventHandler[BaseEvent]] = []
        self.unsupported_command: type[BaseCommand] | None = None
        self.unsupported_event: type[BaseEvent] | None = None

    def command_sender(self, command: BaseCommand) -> None:
        self.seen.append(("command", command.command_id))
        if isinstance(command, GetNotice):
            self.emit(Notice())

    def command_checker(self, command_type: type[BaseCommand]) -> bool:
        return command_type is not self.unsupported_command

    def event_subscriber[E: BaseEvent](
        self, event_type: type[E], handler: EventHandler[E]
    ) -> Callable[[], None]:
        self.seen.append(("subscription", event_type))
        erased = cast(EventHandler[BaseEvent], handler)
        self.handlers.append(erased)
        return lambda: self.handlers.remove(erased)

    def event_checker(self, event_type: type[BaseEvent]) -> bool:
        return event_type is not self.unsupported_event

    def emit(self, event: BaseEvent) -> None:
        for handler in tuple(self.handlers):
            handler(event)


def test_protocol_requires_run_implementation() -> None:
    class MissingRun(BaseProtocol):
        pass

    with pytest.raises(TypeError, match="abstract"):
        MissingRun()  # type: ignore[abstract]


def test_run_forwards_operations_in_call_order_and_retains_handles() -> None:
    environment = RecordingEnvironment()
    context = ProtocolContext(Connection(environment))

    class Example(BaseProtocol):
        def __init__(self) -> None:
            self.received: list[Notice] = []

        def run(self, context: ProtocolContext) -> None:
            self.first = context.require_command(FirstCommand)
            self.first.send(FirstCommand())
            context.require_event(Notice).subscribe(self.received.append)
            context.require_command(SecondCommand).send(SecondCommand())

    protocol = Example()
    assert environment.seen == []
    protocol.run(context)
    assert environment.seen == [
        ("command", "first"), ("subscription", Notice), ("command", "second")
    ]
    protocol.first.send(FirstCommand())
    notice = Notice()
    environment.emit(notice)
    assert protocol.received == [notice]
    assert environment.seen[-1] == ("command", "first")


def test_requirements_do_not_send_or_subscribe_and_recheck_support() -> None:
    environment = RecordingEnvironment()
    context = ProtocolContext(Connection(environment))
    context.require_command(FirstCommand)
    context.require_event(Notice)
    context.require_query(GetNotice)
    assert environment.seen == []

    environment.unsupported_command = FirstCommand
    with pytest.raises(ProtocolSetUpException, match="FirstCommand"):
        context.require_command(FirstCommand)
    environment.unsupported_event = Notice
    with pytest.raises(ProtocolSetUpException, match="Notice"):
        context.require_event(Notice)
    assert environment.seen == []


@pytest.mark.parametrize("reject_command", [True, False])
def test_query_validates_both_capabilities_before_returning_handle(reject_command: bool) -> None:
    environment = RecordingEnvironment()
    if reject_command:
        environment.unsupported_command = GetNotice
    else:
        environment.unsupported_event = Notice
    context = ProtocolContext(Connection(environment))
    with pytest.raises(ProtocolSetUpException):
        context.require_query(GetNotice)
    assert environment.seen == []


def test_failed_requirement_propagates_without_rolling_back_previous_action() -> None:
    environment = RecordingEnvironment()
    environment.unsupported_event = Notice
    context = ProtocolContext(Connection(environment))

    class Example(BaseProtocol):
        def run(self, context: ProtocolContext) -> None:
            context.require_command(FirstCommand).send(FirstCommand())
            context.require_event(Notice)
            context.require_command(SecondCommand).send(SecondCommand())

    with pytest.raises(ProtocolSetUpException, match="Notice"):
        Example().run(context)
    assert environment.seen == [("command", "first")]


def test_subscription_created_during_send_is_installed_immediately() -> None:
    received: list[Notice] = []

    class ReentrantEnvironment(RecordingEnvironment):
        def command_sender(self, command: BaseCommand) -> None:
            super().command_sender(command)
            context.require_event(Notice).subscribe(received.append)
            self.emit(Notice())

    environment = ReentrantEnvironment()
    context = ProtocolContext(Connection(environment))
    context.require_command(FirstCommand).send(FirstCommand())
    assert len(received) == 1
    assert environment.seen == [("command", "first"), ("subscription", Notice)]


def test_plugin_shares_context_and_subscription_can_be_cancelled() -> None:
    class Plugin:
        def __init__(self, context: ProtocolContext) -> None:
            self.received: list[Notice] = []
            self.subscription = context.require_event(Notice).subscribe(self.received.append)

    class Example(BaseProtocol):
        def run(self, context: ProtocolContext) -> None:
            self.plugin = Plugin(context)
            context.require_command(GetNotice).send(GetNotice())

    environment = RecordingEnvironment()
    protocol = Example()
    protocol.run(ProtocolContext(Connection(environment)))
    assert len(protocol.plugin.received) == 1
    protocol.plugin.subscription.unsubscribe()
    environment.emit(Notice())
    assert len(protocol.plugin.received) == 1
    assert environment.handlers == []


def test_query_callback_remains_synchronous_and_one_shot() -> None:
    environment = RecordingEnvironment()
    context = ProtocolContext(Connection(environment))
    received: list[Notice] = []
    context.require_query(GetNotice).request(GetNotice(), received.append)
    assert len(received) == 1
    assert environment.handlers == []
    environment.emit(Notice())
    assert len(received) == 1


def test_environment_send_errors_propagate() -> None:
    class FailingEnvironment(RecordingEnvironment):
        def command_sender(self, command: BaseCommand) -> None:
            raise ValueError("send failed")

    context = ProtocolContext(Connection(FailingEnvironment()))
    with pytest.raises(ValueError, match="send failed"):
        context.require_command(FirstCommand).send(FirstCommand())
