"""Contract under test: the environment seam (bind, Binding, the capability gate).

``bind(cls, provider)`` must (1) recover the declared sets loudly — a silently-empty
set would make the gate vacuous, (2) reject unsupported command declarations BEFORE the
protocol is constructed, (3) enforce one provider per protocol (the provider owns the
bus), and (4) hand back a Binding that owns lifecycle ordering: StartEvent first and
once, StopEvent last and once, nothing delivered outside that window. The timer tests
at the end are the command→event round-trip through the reference environment.
"""

from __future__ import annotations

from typing import Any, Callable

import pytest

from gradys_core import (
    Broadcast,
    CancelTimer,
    GotoCoords,
    MobilityCommand,
    Protocol,
    ScheduleTimer,
    StartEvent,
    TimerEvent,
    UnsupportedCommandError,
    check_capabilities,
    declared_commands,
    declared_events,
)
from gradys_core.events import PacketEvent, StopEvent, TelemetryEvent
from gradys_core.testing import FakeHost

from tests.support import Cmds, Evs, FamilyHost, PoorHost, Recorder, StartStop, Timekeeper

# --------------------------------------------------------------- the capability gate


def test_capability_check_names_the_missing_commands() -> None:
    with pytest.raises(UnsupportedCommandError) as excinfo:
        PoorHost().bind(Recorder)  # Recorder declares timers; PoorHost has none
    message = str(excinfo.value)
    assert "ScheduleTimer" in message
    assert "CancelTimer" in message
    assert "Recorder" in message
    assert "missing" in message


def test_capability_check_passes_on_a_capable_host(host: FakeHost) -> None:
    host.bind(Recorder)  # must not raise


def test_capability_failure_happens_before_the_protocol_is_constructed() -> None:
    constructions: list[int] = []

    class Eager(Protocol[Evs, Cmds]):
        def __init__(self) -> None:
            constructions.append(1)

    with pytest.raises(UnsupportedCommandError):
        PoorHost().bind(Eager)
    assert constructions == []  # a rejected protocol must never run, not even __init__


def test_check_capabilities_accepts_a_collection_with_mro_membership() -> None:
    # A collection containing a base class covers every subclass; core does the MRO walk.
    check_capabilities(
        Recorder, {MobilityCommand, Broadcast, ScheduleTimer, CancelTimer}
    )  # must not raise
    with pytest.raises(UnsupportedCommandError):
        check_capabilities(Recorder, {MobilityCommand, Broadcast})


def test_registry_resolves_a_command_family_through_the_mro() -> None:
    host = FamilyHost()  # registers one handler for all of MobilityCommand
    p: Recorder = host.install(Recorder)
    p.provider.send(GotoCoords(1.0, 2.0, 3.0))
    assert host.seen == [GotoCoords(1.0, 2.0, 3.0)]


# --------------------------------------------------------- declared-set introspection


def test_declared_sets_are_recovered() -> None:
    assert declared_events(Recorder) == (
        StartEvent, StopEvent, TelemetryEvent, PacketEvent, TimerEvent,
    )
    assert declared_commands(Recorder) == (GotoCoords, Broadcast, ScheduleTimer, CancelTimer)


def test_declared_sets_inherit_through_a_subclass() -> None:
    class Derived(Recorder):
        pass

    assert declared_commands(Derived) == declared_commands(Recorder)


def test_declared_sets_handle_a_single_non_union_parameter() -> None:
    class Single(Protocol[TimerEvent, GotoCoords]):
        pass

    assert declared_events(Single) == (TimerEvent,)
    assert declared_commands(Single) == (GotoCoords,)


def test_unparameterized_protocol_subclass_is_a_loud_error() -> None:
    """Returning () here would silently disable the capability gate."""

    class Bare(Protocol):  # type: ignore[type-arg]
        pass

    with pytest.raises(TypeError, match="declares no event/command sets"):
        declared_commands(Bare)
    with pytest.raises(TypeError):
        FakeHost().bind(Bare)


def test_unresolved_parameterization_is_a_loud_error() -> None:
    class Unresolved(Protocol[Any, Any]):
        pass

    with pytest.raises(TypeError, match="cannot be checked"):
        declared_commands(Unresolved)


def test_bind_rejects_a_non_protocol_class() -> None:
    class NotAProtocol:
        pass

    with pytest.raises(TypeError, match="Protocol subclass"):
        FakeHost().bind(NotAProtocol)


# ------------------------------------------------------------------ provider identity


def test_a_provider_binds_exactly_one_protocol(host: FakeHost) -> None:
    """The provider owns the bus, so sharing one across protocols would cross-wire
    their handler chains."""
    from gradys_core import bind

    host.install(Recorder)
    with pytest.raises(RuntimeError, match="already bound"):
        bind(Timekeeper, host.provider)


# -------------------------------------------------------------------------- lifecycle


def test_start_and_stop_are_idempotent(
    host: FakeHost, bound: Callable[[type], Any]
) -> None:
    p: StartStop = bound(StartStop)
    host.binding.start()
    host.binding.stop()
    host.binding.stop()
    assert p.trace.count("start_first") == 1
    assert p.trace.count("stop_second") == 1


def test_stop_without_start_delivers_no_stop_event(host: FakeHost) -> None:
    binding = host.bind(StartStop)
    binding.stop()
    binding.start()  # a closed binding stays closed
    p: StartStop = binding.protocol
    assert p.trace == []


def test_deliver_before_start_is_dropped(host: FakeHost) -> None:
    binding = host.bind(Recorder)
    host.deliver_packet("early", source=1)
    binding.start()
    p: Recorder = binding.protocol
    assert p.trace == []


def test_deliver_after_stop_is_dropped(
    host: FakeHost, bound: Callable[[type], Any]
) -> None:
    p: Recorder = bound(Recorder)
    host.binding.stop()
    host.deliver_packet("x", source=1)
    assert p.trace == []


# ------------------------------------------- timer round-trips (reference environment)


def test_timers_fire_in_order(host: FakeHost, bound: Callable[[type], Any]) -> None:
    p: Timekeeper = bound(Timekeeper)
    p.provider.send(ScheduleTimer("late", 5.0))
    p.provider.send(ScheduleTimer("early", 1.0))
    host.advance(10.0)
    assert p.fired == ["early", "late"]


def test_same_tag_scheduled_twice_keeps_both(
    host: FakeHost, bound: Callable[[type], Any]
) -> None:
    """The embedded runtime dropped the first handle on a same-tag reschedule."""
    p: Timekeeper = bound(Timekeeper)
    p.provider.send(ScheduleTimer("tick", 1.0))
    p.provider.send(ScheduleTimer("tick", 2.0))
    host.advance(5.0)
    assert p.fired == ["tick", "tick"]


def test_cancel_timer_cancels_all_with_that_tag(
    host: FakeHost, bound: Callable[[type], Any]
) -> None:
    p: Timekeeper = bound(Timekeeper)
    p.provider.send(ScheduleTimer("tick", 1.0))
    p.provider.send(ScheduleTimer("tick", 2.0))
    p.provider.send(ScheduleTimer("other", 3.0))
    p.provider.send(CancelTimer("tick"))
    host.advance(5.0)
    assert p.fired == ["other"]


def test_non_positive_delay_fires_at_next_opportunity(
    host: FakeHost, bound: Callable[[type], Any]
) -> None:
    p: Timekeeper = bound(Timekeeper)
    p.provider.send(ScheduleTimer("past", -10.0))
    host.advance(0.0)
    assert p.fired == ["past"]
