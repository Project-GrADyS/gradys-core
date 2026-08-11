"""A deterministic fake environment for tests, plus re-exports of the conformance suite.

:class:`FakeHost` is public API rather than test-only: both downstream projects need a
way to exercise protocols without a simulator or a drone. It is also the reference
implementation of the environment contract — it builds a real
:class:`~gradys_core.protocol.Provider` from its command registry and injects it via
``bind()``, exactly the pattern a real environment uses — and core's own test suite
runs the :class:`~gradys_core.conformance.HostConformance` suite against it.
"""

from __future__ import annotations

import heapq
from typing import Any, Dict, Iterator, List, Optional, Tuple

from gradys_core.commands import (
    Broadcast,
    CancelTimer,
    Command,
    GotoCoords,
    GotoGeoCoords,
    ScheduleTimer,
    SendMessage,
    SetSpeed,
    TrackVariable,
)
from gradys_core.conformance import ConformanceHarness, HostConformance
from gradys_core.events import PacketEvent, TelemetryEvent, TimerEvent
from gradys_core.geometry import Position
from gradys_core.host import Binding, CommandRegistry, bind
from gradys_core.protocol import Provider

__all__ = ["ConformanceHarness", "FakeHost", "HostConformance", "install"]


class FakeHost:
    """A fake environment with a manual clock, an ordered timer queue and captured commands.

    Wires the environment contract the same way a real one does: a
    :class:`CommandRegistry` supplies the provider's ``send``/``supports`` callables,
    the resulting :class:`Provider` is injected through ``bind()``, and events are
    driven through the returned :class:`Binding`. Supports every built-in command.
    Time only moves when :meth:`advance` is called, so tests are deterministic and
    never sleep.
    """

    def __init__(self, node_id: int = 1, start_time: float = 0.0) -> None:
        self._now = start_time
        self._binding: Optional[Binding[Any]] = None
        self._seq = 0
        self._timers: List[Tuple[float, int, str]] = []
        self._cancelled: set[int] = set()
        self._by_tag: Dict[str, List[int]] = {}

        self.commands: List[Command] = []
        """Every command the protocol sent, in order."""

        self.tracked: List[Tuple[str, Any]] = []
        """Every ``TrackVariable`` the protocol sent, as ``(name, value)``."""

        self._registry = CommandRegistry()
        self.register_commands(self._registry)

        self.provider: Provider[Any, Any] = Provider(
            node_id=node_id,
            now=lambda: self._now,
            send=self._registry.dispatch,
            supports=self._registry.supports,
        )
        """The provider this host injects — the environment's runtime surface."""

    # ---------------------------------------------------------------- environment wiring

    def register_commands(self, registry: CommandRegistry) -> None:
        """Populate the registry. Override in a subclass to fake a poorer environment."""
        for command in (GotoCoords, GotoGeoCoords, SetSpeed, SendMessage, Broadcast):
            registry.add(command, self._record)
        registry.add(ScheduleTimer, self._schedule)
        registry.add(CancelTimer, self._cancel)
        registry.add(TrackVariable, self._track)

    def bind(self, protocol_class: type) -> Binding[Any]:
        """Wire ``protocol_class`` to this host without starting it.

        Accepts a legacy ``IProtocol`` subclass and wraps it automatically.
        """
        from gradys_core.legacy import is_legacy, legacy

        if self._binding is not None:
            raise RuntimeError("this FakeHost already has a protocol installed")
        target = legacy(protocol_class) if is_legacy(protocol_class) else protocol_class
        self._binding = bind(target, self.provider)
        return self._binding

    def install(self, protocol_class: type) -> Any:
        """:meth:`bind` then start. Returns the protocol instance."""
        binding = self.bind(protocol_class)
        binding.start()
        return binding.protocol

    # ---------------------------------------------------------------- command handlers

    def _record(self, command: Command) -> None:
        self.commands.append(command)

    def _schedule(self, command: ScheduleTimer) -> None:
        self.commands.append(command)
        self._seq += 1
        # A non-positive delay is legal and fires at the next opportunity.
        when = self._now + max(command.delay, 0.0)
        heapq.heappush(self._timers, (when, self._seq, command.tag))
        self._by_tag.setdefault(command.tag, []).append(self._seq)

    def _cancel(self, command: CancelTimer) -> None:
        self.commands.append(command)
        # Cancel-all: every pending timer carrying this tag.
        self._cancelled.update(self._by_tag.pop(command.tag, ()))

    def _track(self, command: TrackVariable) -> None:
        self.commands.append(command)
        self.tracked.append((command.name, command.value))

    # ---------------------------------------------------------------- test driving

    @property
    def binding(self) -> Binding[Any]:
        if self._binding is None:
            raise RuntimeError("no protocol installed on this host yet")
        return self._binding

    def advance(self, seconds: float) -> None:
        """Move the clock forward, firing every timer due along the way, in order."""
        target = self._now + seconds
        while self._timers and self._timers[0][0] <= target:
            when, seq, tag = heapq.heappop(self._timers)
            pending = self._by_tag.get(tag)
            if pending is not None:
                try:
                    pending.remove(seq)
                except ValueError:
                    pass
                if not pending:
                    self._by_tag.pop(tag, None)
            if seq in self._cancelled:
                self._cancelled.discard(seq)
                continue
            self._now = max(self._now, when)
            self.binding.deliver(TimerEvent(tag))
        self._now = target

    def deliver_packet(self, payload: str, source: int) -> None:
        self.binding.deliver(PacketEvent(payload, source))

    def deliver_telemetry(self, position: Position) -> None:
        self.binding.deliver(TelemetryEvent(position, self._now))

    def pending_timers(self) -> List[str]:
        """Tags of every timer still scheduled, soonest first."""
        return [tag for _, seq, tag in sorted(self._timers) if seq not in self._cancelled]

    def commands_of(self, command_type: type) -> Iterator[Any]:
        """Every captured command of a given type."""
        return (c for c in self.commands if isinstance(c, command_type))

    def clear(self) -> None:
        """Forget captured commands. Timers and the clock are untouched."""
        self.commands.clear()
        self.tracked.clear()


def install(host: FakeHost, protocol_class: type) -> Any:
    """Install ``protocol_class`` on ``host`` and start it. Returns the protocol.

    Accepts a legacy ``IProtocol`` subclass and wraps it automatically.
    """
    return host.install(protocol_class)
