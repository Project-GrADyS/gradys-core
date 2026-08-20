"""Draft 4 — the linker seam of draft 2, over the main implementation.

No Host object. The environment builds a :class:`LinkTable` — supported events as
blank slots, supported commands as provided implementations — and calls
:func:`link`, the analog of ``Protocol.bind`` from draft 2 (core's ``Protocol`` is
untouched, so the linker lives as a module-level function here). ``link`` raises
``RuntimeError`` on undefined symbols, wires a real core ``Provider``/``Binding``
underneath, and fills the declared event slots.

One deliberate difference from draft 2: with the real event bus in play, a filled
slot is the *delivery path* (``Binding.deliver``), not the user's bare handler —
so subscriptions made with ``subscribe()``, priorities, cancellation and the
lifecycle window all keep working. The environment still just calls
``table.events[TelemetryEvent](TelemetryEvent(...))`` and owns its own loop.
"""

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from gradys_core import (
    PRIORITY_PROTOCOL,
    Broadcast,
    Command,
    Event,
    GotoCoords,
    PacketEvent,
    Protocol,
    Provider,
    SetSpeed,
    StartEvent,
    TelemetryEvent,
    bind,
    declared_commands,
    declared_events,
    subscribe,
)

_node_ids = itertools.count()


@dataclass
class LinkTable:
    """What one environment supports, for one node.

    ``events`` maps each producible event to a blank slot (``None``) that
    :func:`link` fills; ``commands`` maps each executable command to the
    implementation the environment already provides.
    """

    events: dict[type[Event], Callable[[Event], None] | None] = field(default_factory=dict)
    commands: dict[type[Command], Callable[[Any], None]] = field(default_factory=dict)


def link(cls: type[Protocol[Any, Any]], table: LinkTable) -> Protocol[Any, Any]:
    """Link ``cls`` against ``table`` — the draft-2 ``Protocol.bind`` analog."""
    missing = [e.__name__ for e in declared_events(cls) if e not in table.events]
    missing += [c.__name__ for c in declared_commands(cls) if c not in table.commands]
    if missing:
        raise RuntimeError(
            f"Cannot link {cls.__name__}: undefined symbols [{', '.join(sorted(missing))}]"
        )

    clock = itertools.count()
    provider = Provider(
        node_id=next(_node_ids),
        now=lambda: float(next(clock)),
        send=lambda cmd: table.commands[type(cmd)](cmd),
        supports=set(table.commands),
    )
    binding = bind(cls, provider)
    binding.start()  # StartEvent first and once; slots only work inside the window
    for event in declared_events(cls):
        table.events[event] = binding.deliver
    return binding.protocol


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
    # The environment (embedded firmware or simulator node) builds its table:
    # blank event slots plus the command implementations it already has.
    table = LinkTable(
        events={StartEvent: None, TelemetryEvent: None, PacketEvent: None},
        commands={
            GotoCoords: lambda cmd: print(f"[motors] {cmd}"),
            Broadcast: lambda cmd: print(f"[radio]  {cmd}"),
        },
    )

    link(SweepProtocol, table)  # StartEvent fires inside link() → GotoCoords printed

    # The environment drives the loop by calling the linked slots directly.
    if slot := table.events[TelemetryEvent]:
        slot(TelemetryEvent(position=(1.0, 2.0, 3.0), timestamp=0.0))
    print(f"[unlinked] PacketEvent slot is still blank: {table.events[PacketEvent]}")

    try:
        link(RacerProtocol, table)  # SetSpeed is not in the table
    except RuntimeError as error:
        print(f"[expected] {error}")
