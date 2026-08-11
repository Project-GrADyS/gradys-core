"""Shared example protocols and hosts for the runtime test suite.

Each class here exists to exercise ONE mechanism, named in its docstring. Tests import
these instead of redefining protocols inline, so a test file only defines a class when
the test is about that class's definition (e.g. the unparameterized-declaration errors).

All protocols follow the real authoring pattern: plain ``__init__`` for their own state
(no ``super().__init__()`` — the base is stateless), subscriptions in ``on_bind()``.
"""

from __future__ import annotations

from typing import List, Optional

from gradys_core import (
    PRIORITY_OBSERVER,
    PRIORITY_PLUGIN,
    PRIORITY_PROTOCOL,
    Broadcast,
    CancelTimer,
    Command,
    Disposition,
    Event,
    GotoCoords,
    MobilityCommand,
    PacketEvent,
    Protocol,
    ScheduleTimer,
    StartEvent,
    StopEvent,
    TelemetryEvent,
    TimerEvent,
    subscribe,
)
from gradys_core.host import CommandRegistry
from gradys_core.testing import FakeHost

Evs = StartEvent | StopEvent | TelemetryEvent | PacketEvent | TimerEvent
Cmds = GotoCoords | Broadcast | ScheduleTimer | CancelTimer
"""The 'full-width' declared sets most examples use: every built-in event, and one
command from each family. Narrower sets are declared inline where the narrowing IS
the point (e.g. capability-gate tests)."""


class Recorder(Protocol[Evs, Cmds]):
    """Exercises handler ORDERING on one event.

    Subscribes four handlers to ``PacketEvent``, one per priority situation: an
    observer, two same-priority plugins (FIFO tie-break), and the protocol's own
    handler. Each appends to ``trace``, so a test reads the exact execution order.
    ``_plugin_b`` returns ``STOP`` for payload ``"mine"``, giving tests a switchable
    chain-truncation point.
    """

    def __init__(self) -> None:
        self.trace: List[str] = []

    def on_bind(self) -> None:
        subscribe(self.provider, PacketEvent, self._observer, PRIORITY_OBSERVER)
        subscribe(self.provider, PacketEvent, self._plugin_a, PRIORITY_PLUGIN)
        subscribe(self.provider, PacketEvent, self._plugin_b, PRIORITY_PLUGIN)
        subscribe(self.provider, PacketEvent, self._own, PRIORITY_PROTOCOL)

    def _observer(self, e: PacketEvent) -> Optional[Disposition]:
        self.trace.append(f"observer:{e.payload}:{e.source}")
        return Disposition.CONTINUE

    def _plugin_a(self, e: PacketEvent) -> Optional[Disposition]:
        self.trace.append("plugin_a")
        return None  # None means CONTINUE

    def _plugin_b(self, e: PacketEvent) -> Optional[Disposition]:
        self.trace.append("plugin_b")
        return Disposition.STOP if e.payload == "mine" else Disposition.CONTINUE

    def _own(self, e: PacketEvent) -> Optional[Disposition]:
        self.trace.append("protocol")
        return None


class StartStop(Protocol[Evs, Cmds]):
    """Exercises the Start/Stop chains: their handlers must ALL run.

    The first handler of each chain returns ``STOP``, which the bus must ignore for
    ``StartEvent``/``StopEvent`` — one plugin must not skip another's setup/teardown.
    """

    def __init__(self) -> None:
        self.trace: List[str] = []

    def on_bind(self) -> None:
        subscribe(self.provider, StartEvent, self._first, PRIORITY_PLUGIN)
        subscribe(self.provider, StartEvent, self._second, PRIORITY_PROTOCOL)
        subscribe(self.provider, StopEvent, self._stop_first, PRIORITY_PLUGIN)
        subscribe(self.provider, StopEvent, self._stop_second, PRIORITY_PROTOCOL)

    def _first(self, e: StartEvent) -> Optional[Disposition]:
        self.trace.append("start_first")
        return Disposition.STOP  # must be ignored

    def _second(self, e: StartEvent) -> Optional[Disposition]:
        self.trace.append("start_second")
        return None

    def _stop_first(self, e: StopEvent) -> Optional[Disposition]:
        self.trace.append(f"stop_first:{e.reason}")
        return Disposition.STOP  # must be ignored

    def _stop_second(self, e: StopEvent) -> Optional[Disposition]:
        self.trace.append("stop_second")
        return None


class Mutator(Protocol[Evs, Cmds]):
    """Exercises mutating the subscription list from INSIDE a running dispatch.

    Its first packet handler cancels itself and registers a new handler; dispatch
    iterates a snapshot, so the change takes effect only from the next event on.
    """

    def __init__(self) -> None:
        self.seen: List[str] = []

    def on_bind(self) -> None:
        self.sub = subscribe(self.provider, PacketEvent, self._first, PRIORITY_PLUGIN)

    def _first(self, e: PacketEvent) -> Optional[Disposition]:
        self.seen.append(f"first:{e.payload}")
        self.sub.cancel()
        subscribe(self.provider, PacketEvent, self._late, PRIORITY_PROTOCOL)
        return Disposition.CONTINUE

    def _late(self, e: PacketEvent) -> Optional[Disposition]:
        self.seen.append(f"late:{e.payload}")
        return None


class CatchAllCounter(Protocol[Event, Cmds]):
    """Exercises base-class (MRO) dispatch by declaring ``Event`` itself.

    Declaring the base is the explicit opt-in to receiving everything — you may
    subscribe to a declared type or a subtype, never a supertype, so a catch-all
    observer has to say so in its declared set.
    """

    def __init__(self) -> None:
        self.count = 0

    def on_bind(self) -> None:
        subscribe(self.provider, Event, self._any, PRIORITY_PROTOCOL)

    def _any(self, e: Event) -> Optional[Disposition]:
        self.count += 1
        return None


class Timekeeper(Protocol[Evs, Cmds]):
    """Records every fired timer tag, for timer round-trip tests."""

    def __init__(self) -> None:
        self.fired: List[str] = []

    def on_bind(self) -> None:
        subscribe(self.provider, TimerEvent, self._on_timer, PRIORITY_PROTOCOL)

    def _on_timer(self, e: TimerEvent) -> Optional[Disposition]:
        self.fired.append(e.tag)
        return None


class PoorHost(FakeHost):
    """A host supporting only mobility-to-a-point and broadcast — NO timers.

    Binding anything that declares ``ScheduleTimer``/``CancelTimer`` (like the shared
    ``Cmds``) must fail the capability gate, naming the missing commands.
    """

    def register_commands(self, registry: CommandRegistry) -> None:
        registry.add(GotoCoords, self._record)
        registry.add(Broadcast, self._record)


class FamilyHost(FakeHost):
    """A host registering ONE handler for the whole ``MobilityCommand`` family.

    Exercises MRO resolution on the command side: sending the concrete ``GotoCoords``
    must land in ``seen`` through the family registration.
    """

    def __init__(self, node_id: int = 1, start_time: float = 0.0) -> None:
        # Created before super().__init__, which calls register_commands below.
        self.seen: List[Command] = []
        super().__init__(node_id=node_id, start_time=start_time)

    def register_commands(self, registry: CommandRegistry) -> None:
        registry.add(MobilityCommand, self.seen.append)
        registry.add(Broadcast, self._record)
        registry.add(ScheduleTimer, self._schedule)
        registry.add(CancelTimer, self._cancel)
