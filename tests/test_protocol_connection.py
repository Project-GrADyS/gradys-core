import asyncio
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

    async def send_command(self, command: BaseCommand) -> None:
        self.seen.append(("command", command.command_id))
        if isinstance(command, GetNotice):
            self.emit(Notice())

    def check_command(self, command_type: type[BaseCommand]) -> bool:
        return command_type is not self.unsupported_command

    def subscribe_to_event[E: BaseEvent](
        self, event_type: type[E], handler: EventHandler[E]
    ) -> Callable[[], None]:
        self.seen.append(("subscription", event_type))
        erased = cast(EventHandler[BaseEvent], handler)
        self.handlers.append(erased)
        return lambda: self.handlers.remove(erased)

    def check_event(self, event_type: type[BaseEvent]) -> bool:
        return event_type is not self.unsupported_event

    def emit(self, event: BaseEvent) -> None:
        for handler in tuple(self.handlers):
            handler(event)


def test_protocol_requires_run_implementation() -> None:
    class MissingRun(BaseProtocol):
        pass

    with pytest.raises(TypeError, match="abstract"):
        MissingRun()  # type: ignore[abstract]


def test_operations_follow_await_order_and_handles_survive_run() -> None:
    environment = RecordingEnvironment()
    context = ProtocolContext(Connection(environment))

    class Example(BaseProtocol):
        def __init__(self) -> None:
            self.received: list[Notice] = []

        async def run(self, context: ProtocolContext) -> None:
            self.first = context.require_command(FirstCommand)
            self.notice = context.require_event(Notice)
            self.second = context.require_command(SecondCommand)

    protocol = Example()
    assert environment.seen == []

    async def exercise_handles() -> None:
        await protocol.run(context)
        assert environment.seen == []
        await protocol.first.send(FirstCommand())
        protocol.notice.subscribe(protocol.received.append)
        await protocol.second.send(SecondCommand())
        assert environment.seen == [
            ("command", "first"), ("subscription", Notice), ("command", "second")
        ]
        await protocol.first.send(FirstCommand())
        notice = Notice()
        environment.emit(notice)
        assert protocol.received == [notice]
        assert environment.seen[-1] == ("command", "first")

    asyncio.run(exercise_handles())


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
        async def run(self, context: ProtocolContext) -> None:
            await context.require_command(FirstCommand).send(FirstCommand())
            context.require_event(Notice)
            await context.require_command(SecondCommand).send(SecondCommand())

    with pytest.raises(ProtocolSetUpException, match="Notice"):
        asyncio.run(Example().run(context))
    assert environment.seen == [("command", "first")]


def test_subscription_created_during_send_is_installed_immediately() -> None:
    received: list[Notice] = []

    class ReentrantEnvironment(RecordingEnvironment):
        async def send_command(self, command: BaseCommand) -> None:
            await super().send_command(command)
            context.require_event(Notice).subscribe(received.append)
            self.emit(Notice())

    environment = ReentrantEnvironment()
    context = ProtocolContext(Connection(environment))
    asyncio.run(context.require_command(FirstCommand).send(FirstCommand()))
    assert len(received) == 1
    assert environment.seen == [("command", "first"), ("subscription", Notice)]


def test_plugin_shares_context_and_subscription_can_be_cancelled() -> None:
    class Plugin:
        def __init__(self, context: ProtocolContext) -> None:
            self.received: list[Notice] = []
            self.subscription = context.require_event(Notice).subscribe(self.received.append)

    class Example(BaseProtocol):
        async def run(self, context: ProtocolContext) -> None:
            self.plugin = Plugin(context)
            self.get_notice = context.require_command(GetNotice)

    environment = RecordingEnvironment()
    protocol = Example()

    async def run_and_send() -> None:
        await protocol.run(ProtocolContext(Connection(environment)))
        await protocol.get_notice.send(GetNotice())

    asyncio.run(run_and_send())
    assert len(protocol.plugin.received) == 1
    protocol.plugin.subscription.unsubscribe()
    environment.emit(Notice())
    assert len(protocol.plugin.received) == 1
    assert environment.handlers == []


def test_query_returns_immediate_response_and_unsubscribes() -> None:
    environment = RecordingEnvironment()
    context = ProtocolContext(Connection(environment))
    response = asyncio.run(context.require_query(GetNotice).request(GetNotice()))
    assert isinstance(response, Notice)
    assert environment.seen == [("subscription", Notice), ("command", "get_notice")]
    assert environment.handlers == []
    environment.emit(Notice())
    assert environment.handlers == []


def test_query_waits_for_delayed_response_and_consumes_only_first_event() -> None:
    async def request_and_respond() -> None:
        sent = asyncio.Event()

        class DelayedEnvironment(RecordingEnvironment):
            async def send_command(self, command: BaseCommand) -> None:
                self.seen.append(("command", command.command_id))
                sent.set()

        environment = DelayedEnvironment()
        context = ProtocolContext(Connection(environment))
        request = asyncio.create_task(context.require_query(GetNotice).request(GetNotice()))
        await sent.wait()
        assert not request.done()
        assert environment.seen == [("subscription", Notice), ("command", "get_notice")]
        response = Notice()
        environment.emit(response)
        environment.emit(Notice())
        assert await request is response
        assert environment.handlers == []

    asyncio.run(asyncio.wait_for(request_and_respond(), timeout=1.0))


def test_run_waits_for_environment_acceptance() -> None:
    async def send_and_accept() -> None:
        entered, accepted = asyncio.Event(), asyncio.Event()

        class DelayedEnvironment(RecordingEnvironment):
            async def send_command(self, command: BaseCommand) -> None:
                entered.set()
                await accepted.wait()
                await super().send_command(command)

        environment = DelayedEnvironment()
        context = ProtocolContext(Connection(environment))

        class Example(BaseProtocol):
            async def run(self, context: ProtocolContext) -> None:
                await context.require_command(FirstCommand).send(FirstCommand())

        sending = asyncio.create_task(Example().run(context))
        await entered.wait()
        assert not sending.done()
        assert environment.seen == []
        accepted.set()
        await sending
        assert environment.seen == [("command", "first")]

    asyncio.run(asyncio.wait_for(send_and_accept(), timeout=1.0))


@pytest.mark.parametrize("query", [False, True])
def test_environment_send_errors_propagate(query: bool) -> None:
    class FailingEnvironment(RecordingEnvironment):
        async def send_command(self, command: BaseCommand) -> None:
            raise ValueError("send failed")

    context = ProtocolContext(Connection(FailingEnvironment()))
    with pytest.raises(ValueError, match="send failed"):
        if query:
            asyncio.run(context.require_query(GetNotice).request(GetNotice()))
        else:
            asyncio.run(context.require_command(FirstCommand).send(FirstCommand()))
