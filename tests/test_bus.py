"""Contract under test: event dispatch semantics (the bus behind ``subscribe``).

Handlers run in ``(priority, registration order)``; ``STOP`` consumes an event except
for Start/Stop chains; matching walks the event's MRO; dispatch iterates a snapshot so
handlers may subscribe/cancel mid-dispatch. These semantics are what protocol and
plugin authors program against, and must be identical in every execution environment —
which is why the bus is core-owned and only tested here, through the public surface.
"""

from __future__ import annotations

from typing import Any, Callable

from gradys_core.testing import FakeHost

from tests.support import CatchAllCounter, Mutator, Recorder, StartStop


def test_priority_bands_run_low_to_high_and_ties_break_fifo(
    host: FakeHost, bound: Callable[[type], Any]
) -> None:
    p: Recorder = bound(Recorder)
    host.deliver_packet("other", source=3)
    assert p.trace == ["observer:other:3", "plugin_a", "plugin_b", "protocol"]


def test_stop_truncates_the_rest_of_the_chain(
    host: FakeHost, bound: Callable[[type], Any]
) -> None:
    p: Recorder = bound(Recorder)
    host.deliver_packet("mine", source=4)  # _plugin_b STOPs on "mine"
    assert p.trace == ["observer:mine:4", "plugin_a", "plugin_b"]


def test_packet_event_carries_the_sender(
    host: FakeHost, bound: Callable[[type], Any]
) -> None:
    p: Recorder = bound(Recorder)
    host.deliver_packet("hi", source=42)
    assert p.trace[0] == "observer:hi:42"


def test_start_and_stop_chains_ignore_stop_disposition(
    host: FakeHost, bound: Callable[[type], Any]
) -> None:
    p: StartStop = bound(StartStop)
    assert p.trace == ["start_first", "start_second"]  # STOP from _first ignored
    host.binding.stop("done")
    assert p.trace[-2:] == ["stop_first:done", "stop_second"]


def test_mro_dispatch_reaches_base_class_subscribers(
    host: FakeHost, bound: Callable[[type], Any]
) -> None:
    p: CatchAllCounter = bound(CatchAllCounter)
    assert p.count == 1  # StartEvent
    host.deliver_packet("x", source=1)
    host.deliver_telemetry((0.0, 0.0, 0.0))
    assert p.count == 3


def test_subscribing_and_cancelling_during_dispatch_take_effect_next_event(
    host: FakeHost, bound: Callable[[type], Any]
) -> None:
    p: Mutator = bound(Mutator)
    host.deliver_packet("a", source=1)
    # `_late` was added mid-dispatch, so it is not called for this event...
    assert p.seen == ["first:a"]
    host.deliver_packet("b", source=1)
    # ...but is from the next one, and `_first` is now cancelled.
    assert p.seen == ["first:a", "late:b"]


def test_cancel_is_idempotent(host: FakeHost, bound: Callable[[type], Any]) -> None:
    p: Mutator = bound(Mutator)
    p.sub.cancel()
    p.sub.cancel()
    assert not p.sub.active
