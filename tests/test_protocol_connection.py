from dataclasses import dataclass

import pytest

from gradys_core.command import BaseCommand
from gradys_core.event import BaseEvent, EventHandler
from gradys_core.protocol import BaseProtocol


class FirstCommand(BaseCommand):
    command_id = "first"


class SecondCommand(BaseCommand):
    command_id = "second"


@dataclass
class Notice(BaseEvent):
    event_id = "notice"


class RecordingEnvironment:
    """Satisfy the environment interface without inheriting from its Protocol."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, object]] = []

    def command_sender(self, command: BaseCommand) -> None:
        self.seen.append(("command", command.command_id))

    def command_checker(self, command_type: type[BaseCommand]) -> bool:
        return True

    def event_subscriber[E: BaseEvent](self, event_type: type[E], handler: EventHandler[E]) -> None:
        self.seen.append(("subscription", event_type))

    def event_checker(self, event_type: type[BaseEvent]) -> bool:
        return True


def test_injection_installs_subscriptions_then_flushes_commands_in_shared_order() -> None:
    protocol = BaseProtocol()
    first = protocol.require_command(FirstCommand)
    second = protocol.require_command(SecondCommand)
    event = protocol.require_event(Notice)
    environment = RecordingEnvironment()

    first.send(FirstCommand())
    second.send(SecondCommand())
    event.subscribe(lambda _: None)
    first.send(FirstCommand())

    protocol._inject(environment)

    assert environment.seen == [
        ("subscription", Notice),
        ("command", "first"),
        ("command", "second"),
        ("command", "first"),
    ]


def test_post_injection_requests_forward_immediately() -> None:
    protocol = BaseProtocol()
    command = protocol.require_command(FirstCommand)
    event = protocol.require_event(Notice)
    environment = RecordingEnvironment()
    protocol._inject(environment)

    command.send(FirstCommand())
    event.subscribe(lambda _: None)

    assert [entry[0] for entry in environment.seen] == ["command", "subscription"]


def test_duplicate_injection_is_rejected() -> None:
    protocol = BaseProtocol()
    environment = RecordingEnvironment()
    protocol._inject(environment)

    with pytest.raises(RuntimeError, match="already been injected"):
        protocol._inject(environment)


def test_reentrant_command_is_queued_after_existing_commands() -> None:
    protocol = BaseProtocol()
    first = protocol.require_command(FirstCommand)
    second = protocol.require_command(SecondCommand)
    sent: list[str] = []

    first.send(FirstCommand())
    second.send(SecondCommand())

    class ReentrantEnvironment(RecordingEnvironment):
        def command_sender(self, command: BaseCommand) -> None:
            sent.append(command.command_id)
            if len(sent) == 1:
                first.send(FirstCommand())

    protocol._inject(ReentrantEnvironment())
    assert sent == ["first", "second", "first"]


def test_subscription_added_by_last_command_installs_before_its_new_command() -> None:
    protocol = BaseProtocol()
    first = protocol.require_command(FirstCommand)
    second = protocol.require_command(SecondCommand)
    notice = protocol.require_event(Notice)
    first.send(FirstCommand())

    class ReentrantEnvironment(RecordingEnvironment):
        def command_sender(self, command: BaseCommand) -> None:
            super().command_sender(command)
            if command.command_id == "first":
                notice.subscribe(lambda _: None)

        def event_subscriber[E: BaseEvent](self, event_type: type[E], handler: EventHandler[E]) -> None:
            super().event_subscriber(event_type, handler)
            second.send(SecondCommand())

    environment = ReentrantEnvironment()
    protocol._inject(environment)

    assert environment.seen == [
        ("command", "first"),
        ("subscription", Notice),
        ("command", "second"),
    ]


def test_failed_injection_cannot_be_retried_and_replay_side_effects() -> None:
    protocol = BaseProtocol()
    command = protocol.require_command(FirstCommand)
    sent: list[BaseCommand] = []
    command.send(FirstCommand())

    class FailingEnvironment(RecordingEnvironment):
        def command_sender(self, command: BaseCommand) -> None:
            sent.append(command)
            raise ValueError("environment failed")

    environment = FailingEnvironment()
    with pytest.raises(ValueError, match="environment failed"):
        protocol._inject(environment)
    with pytest.raises(RuntimeError, match="already been injected"):
        protocol._inject(environment)
    assert len(sent) == 1
