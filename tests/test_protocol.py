"""Contract under test: the protocol-author surface (Protocol, Provider, subscribe).

A protocol is stateless at the base: ``provider`` is injected by ``bind()``, so authors
never call ``super().__init__()`` and must not touch the provider from ``__init__``.
Everything the environment offers flows through the provider: identity, the node
clock, ``send`` (with a runtime backstop mirroring the static command check), and the
bus behind ``subscribe`` (with a runtime backstop mirroring the static event-membership
check, for untyped callers).
"""

from __future__ import annotations

from typing import Any, Callable, cast

import pytest

from gradys_core import (
    PRIORITY_PROTOCOL,
    Broadcast,
    GotoCoords,
    NotInstalledError,
    PacketEvent,
    Protocol,
    ScheduleTimer,
    TimerEvent,
    UndeclaredEventError,
    UnsupportedCommandError,
    subscribe,
)
from gradys_core.events import Event
from gradys_core.testing import FakeHost

from tests.support import Cmds, Evs, PoorHost, Recorder


def test_provider_exposes_identity_and_the_node_clock() -> None:
    host = FakeHost(node_id=9, start_time=100.0)
    p: Recorder = host.install(Recorder)
    assert p.provider.node_id() == 9
    assert p.provider.now() == 100.0
    host.advance(2.5)
    assert p.provider.now() == 102.5


def test_send_routes_commands_to_the_environment(
    host: FakeHost, bound: Callable[[type], Any]
) -> None:
    p: Recorder = bound(Recorder)
    p.provider.send(GotoCoords(1.0, 2.0, 3.0))
    p.provider.send(ScheduleTimer("tick", 1.0))
    assert GotoCoords(1.0, 2.0, 3.0) in host.commands
    assert ScheduleTimer("tick", 1.0) in host.commands


def test_send_of_an_unsupported_command_is_a_uniform_runtime_error() -> None:
    """Backstop of the static check: an untyped caller sending a command the
    environment cannot service gets UnsupportedCommandError from the provider itself,
    regardless of what the environment's send callable would have done."""

    class Narrow(Protocol[Evs, GotoCoords | Broadcast]):
        pass

    host = PoorHost()  # supports exactly GotoCoords and Broadcast
    p: Narrow = host.install(Narrow)
    send_untyped = cast(Callable[[Any], None], p.provider.send)
    with pytest.raises(UnsupportedCommandError, match="ScheduleTimer"):
        send_untyped(ScheduleTimer("tick", 1.0))


def test_subscribing_an_undeclared_event_is_a_runtime_error_for_untyped_callers(
    host: FakeHost, bound: Callable[[type], Any]
) -> None:
    """Backstop of the static membership check (mypy reports it poorly as
    'Cannot infer value of type parameter _E'; this raises with the declared set)."""

    class SensorEvent(Event):
        pass

    def handler(e: SensorEvent) -> None:
        return None

    p: Recorder = bound(Recorder)
    subscribe_untyped = cast(Callable[..., Any], subscribe)
    with pytest.raises(UndeclaredEventError, match="SensorEvent"):
        subscribe_untyped(p.provider, SensorEvent, handler)


def test_subscribing_a_subtype_of_a_declared_event_is_allowed(
    host: FakeHost, bound: Callable[[type], Any]
) -> None:
    """Subtype-yes: mirrors the static rule (you may narrow, never widen)."""

    class TaggedTimer(TimerEvent):
        pass

    p: Recorder = bound(Recorder)
    sub = subscribe(p.provider, TaggedTimer, lambda e: None)
    assert sub.active


def test_touching_provider_before_bind_is_a_clear_error() -> None:
    p = Recorder()
    with pytest.raises(NotInstalledError, match="on_bind"):
        p.provider.node_id()


def test_protocols_need_no_super_init() -> None:
    """The base is stateless: a protocol's own plain __init__ is enough."""

    class Stateful(Protocol[Evs, Cmds]):
        def __init__(self) -> None:  # note: no super().__init__()
            self.count = 0

        def on_bind(self) -> None:
            subscribe(self.provider, PacketEvent, self._on_packet, PRIORITY_PROTOCOL)

        def _on_packet(self, e: PacketEvent) -> None:
            self.count += 1

    host = FakeHost()
    p: Stateful = host.install(Stateful)
    host.deliver_packet("x", source=1)
    assert p.count == 1


def test_on_bind_runs_exactly_once_and_after_injection(host: FakeHost) -> None:
    class Probe(Protocol[Evs, Cmds]):
        def __init__(self) -> None:
            self.bind_calls = 0

        def on_bind(self) -> None:
            self.provider.node_id()  # must not raise: provider injected first
            self.bind_calls += 1

    p: Probe = host.install(Probe)
    assert p.bind_calls == 1


def test_a_protocol_subclass_extends_subscriptions_via_super_on_bind(
    host: FakeHost, bound: Callable[[type], Any]
) -> None:
    """Opt-in composition: unlike the old universal super().__init__(), only a
    protocol subclassing another protocol calls super(), and only in on_bind."""

    class Derived(Recorder):
        def on_bind(self) -> None:
            super().on_bind()  # keep Recorder's four packet handlers
            subscribe(self.provider, TimerEvent, self._on_timer, PRIORITY_PROTOCOL)

        def _on_timer(self, e: TimerEvent) -> None:
            self.trace.append(f"timer:{e.tag}")

    p: Derived = bound(Derived)
    host.deliver_packet("x", source=1)
    p.provider.send(ScheduleTimer("lap", 1.0))
    host.advance(2.0)
    assert p.trace == ["observer:x:1", "plugin_a", "plugin_b", "protocol", "timer:lap"]
