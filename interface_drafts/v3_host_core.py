"""Draft 3 — the hosted seam of draft 1, over the main implementation.

Same environment surface as ``v1_host.py`` — a ``Host`` with exactly

    host.register_listener(CommandType, fn)
    host.bind(UserProtocolSubclass)
    host.deliver(event)

— but the authoring surface is the real library's: ``Protocol[Events, Commands]``
generics, module-level ``subscribe(provider, event, handler)`` called from
``on_bind()``, and ``self.provider.send(command)``. The Host is a thin wrapper that
composes existing core pieces (``CommandRegistry``, ``Provider``, ``bind``,
``Binding``) instead of reimplementing dispatch, so the capability gate, lifecycle
ordering (StartEvent first) and bus priorities all come for free.
"""

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from collections.abc import Callable, Iterable
from typing import Any

from gradys_core import (
    PRIORITY_PROTOCOL,
    Binding,
    Broadcast,
    Command,
    CommandRegistry,
    Event,
    GotoCoords,
    Protocol,
    Provider,
    SetSpeed,
    StartEvent,
    TelemetryEvent,
    UnsupportedCommandError,
    bind,
    declared_events,
    subscribe,
)


class Host:
    """One host per node, wrapping the core seam behind the three-method interface."""

    def __init__(self, node_id: int, supported_events: Iterable[type[Event]]) -> None:
        self._node_id = node_id
        self._supported_events = tuple(supported_events)
        self._registry = CommandRegistry()
        self._clock = itertools.count()  # stand-in for the environment's real clock
        self._binding: Binding[Any] | None = None

    def register_listener(
        self, command_type: type[Command], fn: Callable[[Any], None]
    ) -> None:
        """Environment side: 'when the protocol issues this command, run fn'."""
        self._registry.add(command_type, fn)

    def bind(self, protocol_cls: type[Protocol[Any, Any]]) -> Protocol[Any, Any]:
        """Check capabilities, wire a Provider from this host's parts, start lifecycle."""
        missing = [
            e for e in declared_events(protocol_cls)
            if not any(issubclass(e, s) for s in self._supported_events)
        ]
        if missing:
            raise RuntimeError(
                f"{protocol_cls.__name__} declares event(s) this host never produces: "
                f"{', '.join(m.__name__ for m in missing)}"
            )
        provider = Provider(
            node_id=self._node_id,
            now=lambda: float(next(self._clock)),
            send=self._registry.dispatch,
            supports=self._registry.supports,  # command gate runs inside core's bind()
        )
        self._binding = bind(protocol_cls, provider)
        self._binding.start()  # StartEvent first and once, per the lifecycle contract
        return self._binding.protocol

    def deliver(self, event: Event) -> None:
        """Push an event into the bound protocol through the core Binding."""
        if self._binding is None:
            raise RuntimeError("deliver() before bind()")
        self._binding.deliver(event)


# ---------------------------------------------------------------------------
# Demo — the protocol is written exactly like against the main library
# ---------------------------------------------------------------------------

SweepEvents = StartEvent | TelemetryEvent
SweepCommands = GotoCoords | Broadcast


class SweepProtocol(Protocol[SweepEvents, SweepCommands]):
    def on_bind(self) -> None:
        subscribe(self.provider, StartEvent, self._on_start, PRIORITY_PROTOCOL)
        subscribe(self.provider, TelemetryEvent, self._on_telemetry, PRIORITY_PROTOCOL)

    def _on_start(self, e: StartEvent) -> None:
        self.provider.send(GotoCoords(10.0, 20.0, 30.0))

    def _on_telemetry(self, e: TelemetryEvent) -> None:
        self.provider.send(Broadcast(f"at {e.position}"))


class RacerProtocol(Protocol[StartEvent, SetSpeed]):
    def on_bind(self) -> None:
        subscribe(self.provider, StartEvent, self._on_start, PRIORITY_PROTOCOL)

    def _on_start(self, e: StartEvent) -> None:
        self.provider.send(SetSpeed(99.0))


if __name__ == "__main__":
    host = Host(node_id=0, supported_events=(StartEvent, TelemetryEvent))
    host.register_listener(GotoCoords, lambda cmd: print(f"[motors] {cmd}"))
    host.register_listener(Broadcast, lambda cmd: print(f"[radio]  {cmd}"))

    host.bind(SweepProtocol)  # StartEvent fires here → GotoCoords hits the listener
    host.deliver(TelemetryEvent(position=(1.0, 2.0, 3.0), timestamp=0.0))

    try:
        host.bind(RacerProtocol)  # no SetSpeed listener registered
    except UnsupportedCommandError as error:
        print(f"[expected] {error}")
