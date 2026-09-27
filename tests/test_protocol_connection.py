from dataclasses import dataclass

import pytest

from gradys_core.command import BaseCommand
from gradys_core.event import BaseEvent
from gradys_core.protocol import BaseProtocol, InjectionPackage


class FirstCommand(BaseCommand):
    command_id = "first"


class SecondCommand(BaseCommand):
    command_id = "second"


@dataclass
class Notice(BaseEvent):
    event_id = "notice"


def test_injection_installs_subscriptions_then_flushes_commands_in_shared_order():
    protocol = BaseProtocol()
    first = protocol.require_command(FirstCommand)
    second = protocol.require_command(SecondCommand)
    event = protocol.require_event(Notice)
    seen = []

    first.send(FirstCommand())
    second.send(SecondCommand())
    event.subscribe(lambda _: None)
    first.send(FirstCommand())

    protocol._inject(InjectionPackage(
        command_sender=lambda command: seen.append(("command", command.command_id)),
        event_subscriber=lambda event_type, handler: seen.append(("subscription", event_type)),
    ))

    assert seen == [
        ("subscription", Notice),
        ("command", "first"),
        ("command", "second"),
        ("command", "first"),
    ]


def test_post_injection_requests_forward_immediately():
    protocol = BaseProtocol()
    command = protocol.require_command(FirstCommand)
    event = protocol.require_event(Notice)
    seen = []
    protocol._inject(InjectionPackage(
        command_sender=lambda value: seen.append(("command", value)),
        event_subscriber=lambda event_type, handler: seen.append(("subscription", event_type)),
    ))

    command.send(FirstCommand())
    event.subscribe(lambda _: None)

    assert [entry[0] for entry in seen] == ["command", "subscription"]


def test_duplicate_injection_is_rejected():
    protocol = BaseProtocol()
    package = InjectionPackage(lambda _: None, lambda _event, _handler: None)
    protocol._inject(package)

    with pytest.raises(RuntimeError, match="already injected"):
        protocol._inject(package)


def test_reentrant_command_is_queued_after_existing_commands():
    protocol = BaseProtocol()
    first = protocol.require_command(FirstCommand)
    second = protocol.require_command(SecondCommand)
    sent = []

    first.send(FirstCommand())
    second.send(SecondCommand())

    def send(command):
        sent.append(command.command_id)
        if len(sent) == 1:
            first.send(FirstCommand())

    protocol._inject(InjectionPackage(send, lambda _event, _handler: None))
    assert sent == ["first", "second", "first"]


def test_subscription_added_by_last_command_installs_before_its_new_command():
    protocol = BaseProtocol()
    first = protocol.require_command(FirstCommand)
    second = protocol.require_command(SecondCommand)
    notice = protocol.require_event(Notice)
    seen = []
    first.send(FirstCommand())

    def send(command):
        seen.append(("command", command.command_id))
        if command.command_id == "first":
            notice.subscribe(lambda _: None)

    def subscribe(event_type, handler):
        seen.append(("subscription", event_type))
        second.send(SecondCommand())

    protocol._inject(InjectionPackage(
        command_sender=send,
        event_subscriber=subscribe,
    ))

    assert seen == [
        ("command", "first"),
        ("subscription", Notice),
        ("command", "second"),
    ]


def test_failed_injection_cannot_be_retried_and_replay_side_effects():
    protocol = BaseProtocol()
    command = protocol.require_command(FirstCommand)
    sent = []
    command.send(FirstCommand())

    def fail(command):
        sent.append(command)
        raise ValueError("environment failed")

    package = InjectionPackage(fail, lambda _event, _handler: None)
    with pytest.raises(ValueError, match="environment failed"):
        protocol._inject(package)
    with pytest.raises(RuntimeError, match="already injected"):
        protocol._inject(package)
    assert len(sent) == 1
