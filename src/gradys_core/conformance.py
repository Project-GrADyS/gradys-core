"""The host conformance suite: the executable contract every execution environment passes.

The environment contract has two halves. :func:`gradys_core.bind` enforces the
structural half (capability gate, lifecycle ordering) by construction; this module is
the behavioral half — the checks that keep the simulator and the embedded runtime from
drifting apart again. Each environment implements one small
:class:`ConformanceHarness` in its own test tree and subclasses
:class:`HostConformance`::

    # in your environment's tests, collected by pytest as usual
    class TestMyEnvironmentConformance(HostConformance):
        supports_timers = True

        def make_harness(self) -> ConformanceHarness:
            return MyEnvironmentHarness()

Assumptions the suite makes about the environment: it supports
:class:`~gradys_core.commands.Broadcast` (every probe protocol declares it or a
sibling). Mobility coverage is on by default (``supports_mobility``); timer coverage is
opt-in (``supports_timers``).

The module deliberately imports nothing outside the standard library and gradys-core,
so importing :mod:`gradys_core.testing` never drags in pytest.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, List, NoReturn, Optional, Sequence, cast

from gradys_core.bus import PRIORITY_PROTOCOL, Disposition
from gradys_core.commands import (
    Broadcast,
    CancelTimer,
    Command,
    GotoCoords,
    ScheduleTimer,
)
from gradys_core.events import Event, PacketEvent, StartEvent, StopEvent, TimerEvent
from gradys_core.host import Binding, UnsupportedCommandError
from gradys_core.protocol import Protocol, subscribe

__all__ = ["ConformanceHarness", "HostConformance", "ProbeCommand"]

_PING = "gradys-core-conformance-ping"


# ------------------------------------------------------------------- probe protocols


@dataclass(frozen=True)
class ProbeCommand(Command):
    """A command no environment supports. The capability gate must reject it.

    If your environment's ``supports`` answer admits this class, it is not answering
    truthfully (for example, a predicate that always returns True).
    """


class _NeverServiceable(Protocol[StartEvent, ProbeCommand]):
    """Declares :class:`ProbeCommand`; binding it anywhere must fail."""

    constructions: ClassVar[int] = 0

    def __init__(self) -> None:
        _NeverServiceable.constructions += 1


class _LifecycleProbe(Protocol[Event, Broadcast]):
    """Records every event it sees, in order."""

    def __init__(self) -> None:
        self.seen: List[Event] = []

    def on_bind(self) -> None:
        subscribe(self.provider, Event, self._on_any, PRIORITY_PROTOCOL)

    def _on_any(self, e: Event) -> Optional[Disposition]:
        self.seen.append(e)
        return None


class _CommandSender(Protocol[StartEvent, Broadcast]):
    """Sends one Broadcast as soon as it starts."""

    def on_bind(self) -> None:
        subscribe(self.provider, StartEvent, self._go, PRIORITY_PROTOCOL)

    def _go(self, e: StartEvent) -> None:
        self.provider.send(Broadcast(_PING))


class _MobilityProbe(Protocol[StartEvent, GotoCoords]):
    """Declares a concrete member of the mobility family.

    An environment supporting the family base
    (:class:`~gradys_core.commands.MobilityCommand`) must admit and execute it — the
    MRO resolution the contract promises.
    """

    def on_bind(self) -> None:
        subscribe(self.provider, StartEvent, self._go, PRIORITY_PROTOCOL)

    def _go(self, e: StartEvent) -> None:
        self.provider.send(GotoCoords(7.0, 8.0, 9.0))


_TimerEvents = StartEvent | TimerEvent
_TimerCommands = ScheduleTimer | CancelTimer


class _TimerProbe(Protocol[_TimerEvents, _TimerCommands]):
    """Schedules three timers, cancels one tag, records what fires."""

    def __init__(self) -> None:
        self.fired: List[str] = []

    def on_bind(self) -> None:
        subscribe(self.provider, StartEvent, self._go, PRIORITY_PROTOCOL)
        subscribe(self.provider, TimerEvent, self._on_timer, PRIORITY_PROTOCOL)

    def _go(self, e: StartEvent) -> None:
        send = self.provider.send
        send(ScheduleTimer("gradys-conf-keep", 1.0))
        send(ScheduleTimer("gradys-conf-cancelled", 1.0))
        send(ScheduleTimer("gradys-conf-cancelled", 2.0))
        send(CancelTimer("gradys-conf-cancelled"))       # cancel-all by tag
        send(ScheduleTimer("gradys-conf-now", 0.0))      # non-positive delay is legal

    def _on_timer(self, e: TimerEvent) -> None:
        self.fired.append(e.tag)


# ------------------------------------------------------------------------ the harness


class ConformanceHarness(ABC):
    """What an environment's test code provides so the suite can drive it.

    One harness instance backs one test, so :meth:`bind` will be called at most once
    per instance.
    """

    @abstractmethod
    def bind(self, protocol_cls: type) -> Binding[Any]:
        """Wire ``protocol_cls`` to the real environment, without starting it.

        Must go through :func:`gradys_core.bind` with a
        :class:`~gradys_core.protocol.Provider` built from the environment's real
        wiring (its actual ``send``/``supports``/clock).
        """

    @abstractmethod
    def executed(self) -> Sequence[Command]:
        """The commands the environment has finished executing, in order.

        An asynchronous environment must drain whatever loop or queue it uses before
        returning, so that every command already sent by the protocol is visible.
        """

    def advance(self, seconds: float) -> None:
        """Let ``seconds`` of environment time pass. Required when timers are covered."""
        raise NotImplementedError(
            f"{type(self).__name__} sets supports_timers but implements no advance()"
        )


def _skip(reason: str) -> None:
    """pytest.skip when pytest is present; silently pass otherwise."""
    try:
        import pytest
    except ImportError:
        return
    pytest.skip(reason)


def _fail(message: str) -> NoReturn:
    raise AssertionError(message)


class HostConformance(ABC):
    """Subclass this in your environment's test tree; pytest collects the checks.

    Class attributes:
        supports_mobility: cover MRO resolution through the mobility family.
        supports_timers: cover the ScheduleTimer/CancelTimer/TimerEvent round-trip;
            requires the harness to implement ``advance()``.
    """

    supports_mobility: ClassVar[bool] = True
    supports_timers: ClassVar[bool] = False

    @abstractmethod
    def make_harness(self) -> ConformanceHarness:
        """Return a fresh harness wired to the real environment."""

    # -------------------------------------------------------------- capability gate

    def test_unsupported_command_fails_before_construction(self) -> None:
        harness = self.make_harness()
        before = _NeverServiceable.constructions
        try:
            harness.bind(_NeverServiceable)
        except UnsupportedCommandError:
            pass
        else:
            _fail(
                "bind() must raise UnsupportedCommandError for a protocol declaring "
                "ProbeCommand — the environment's `supports` answer admitted a "
                "command it cannot service"
            )
        assert _NeverServiceable.constructions == before, (
            "the rejected protocol was constructed; the capability check must run "
            "before the protocol class is instantiated"
        )

    # ------------------------------------------------------------------- lifecycle

    def test_start_event_is_first_and_delivered_once(self) -> None:
        harness = self.make_harness()
        binding = harness.bind(_LifecycleProbe)
        probe = cast(_LifecycleProbe, binding.protocol)
        binding.deliver(PacketEvent("too-early", source=0))  # must be dropped
        binding.start()
        binding.start()  # idempotent
        assert [type(e) for e in probe.seen] == [StartEvent], (
            "a protocol must observe exactly one StartEvent, before any other event"
        )

    def test_stop_event_is_last_and_delivered_once(self) -> None:
        harness = self.make_harness()
        binding = harness.bind(_LifecycleProbe)
        probe = cast(_LifecycleProbe, binding.protocol)
        binding.start()
        binding.deliver(PacketEvent("mid-flight", source=0))
        binding.stop("conformance")
        binding.stop("again")  # idempotent
        binding.deliver(PacketEvent("too-late", source=0))  # must be dropped
        assert [type(e) for e in probe.seen] == [StartEvent, PacketEvent, StopEvent], (
            "a protocol must observe exactly one StopEvent, after every other event"
        )

    def test_stop_without_start_delivers_no_stop_event(self) -> None:
        harness = self.make_harness()
        binding = harness.bind(_LifecycleProbe)
        probe = cast(_LifecycleProbe, binding.protocol)
        binding.stop()
        binding.start()  # a closed binding stays closed
        assert probe.seen == [], (
            "a protocol must never observe a StopEvent without its matching "
            "StartEvent, and a stopped binding must not restart"
        )

    # -------------------------------------------------------------------- commands

    def test_commands_reach_the_environment(self) -> None:
        harness = self.make_harness()
        harness.bind(_CommandSender).start()
        assert Broadcast(_PING) in harness.executed(), (
            "a command sent by the protocol never reached the environment's executor"
        )

    def test_command_families_resolve_through_the_mro(self) -> None:
        if not self.supports_mobility:
            _skip("environment declares no mobility support")
        harness = self.make_harness()
        harness.bind(_MobilityProbe).start()
        assert GotoCoords(7.0, 8.0, 9.0) in harness.executed(), (
            "an environment supporting the mobility family must admit and execute "
            "its concrete members (MRO resolution)"
        )

    # ---------------------------------------------------------------------- timers

    def test_timer_round_trip_and_cancel_all(self) -> None:
        if not self.supports_timers:
            _skip("environment declares no timer support")
        harness = self.make_harness()
        binding = harness.bind(_TimerProbe)
        probe = cast(_TimerProbe, binding.protocol)
        binding.start()
        harness.advance(3.0)
        assert probe.fired.count("gradys-conf-keep") == 1, (
            "a ScheduleTimer the environment accepted must produce exactly one "
            "TimerEvent with its tag"
        )
        assert probe.fired.count("gradys-conf-now") == 1, (
            "a non-positive delay is legal and fires at the next opportunity"
        )
        assert "gradys-conf-cancelled" not in probe.fired, (
            "CancelTimer must cancel every pending timer carrying its tag"
        )
