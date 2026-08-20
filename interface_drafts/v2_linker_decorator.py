"""Draft 2 — no Host: ``Protocol.bind`` as an analog of a C linker.

There is no Host object in core. gradys-embedded and gradys-sim NG manipulate the
Protocol class directly through a single seam, ``Protocol.bind(table)``, which
behaves like a linker resolving symbols:

* The environment hands ``bind`` a :class:`LinkTable` — its table of supported
  events (blank slots, to be filled) and supported commands (implementations
  already provided, e.g. motors on embedded, physics on the simulator).
* ``bind`` fills each blank event slot with the user's ``@subscribe`` handler and
  wires each ``command()`` attribute to the environment's implementation.
* A requirement absent from the table is an undefined symbol → ``RuntimeError``.

After linking, the environment owns the loop and simply calls the filled slots:
``table.events[Telemetry](Telemetry(...))``.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class Event:
    pass


class Command:
    pass


# ---------------------------------------------------------------------------
# Authoring helpers (same surface as draft 1)
# ---------------------------------------------------------------------------

def subscribe(event: type[Event]) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark a method as the handler for ``event``; collected at class creation."""

    def decorate(method: Callable[..., Any]) -> Callable[..., Any]:
        setattr(method, "required_event", event)
        return method

    return decorate


def command(command_type: type[Command]) -> Callable[..., None]:
    """Declare an outgoing command; ``bind`` links it to the table's implementation."""

    def send(self: "Protocol", *args: Any, **kwargs: Any) -> None:
        self._table.commands[command_type](command_type(*args, **kwargs))

    send.required_command = command_type  # type: ignore[attr-defined]
    return send


# ---------------------------------------------------------------------------
# The linker seam
# ---------------------------------------------------------------------------

@dataclass
class LinkTable:
    """What one environment supports, for one node.

    ``events`` maps each producible event to a blank slot (``None``) that
    ``bind`` fills; ``commands`` maps each executable command to the
    implementation the environment already provides.
    """

    events: dict[type[Event], Callable[[Event], None] | None] = field(default_factory=dict)
    commands: dict[type[Command], Callable[[Command], None]] = field(default_factory=dict)


class Protocol:
    """Base class: requirements are derived from usage sites, never declared."""

    required_events: set[type[Event]] = set()
    required_commands: set[type[Command]] = set()
    _table: LinkTable

    def __init_subclass__(cls) -> None:
        cls.required_events = set().union(
            *(base.required_events for base in cls.__bases__ if issubclass(base, Protocol))
        )
        cls.required_commands = set().union(
            *(base.required_commands for base in cls.__bases__ if issubclass(base, Protocol))
        )
        for member in vars(cls).values():
            if event := getattr(member, "required_event", None):
                cls.required_events.add(event)
            if command_type := getattr(member, "required_command", None):
                cls.required_commands.add(command_type)

    @classmethod
    def bind(cls, table: LinkTable) -> "Protocol":
        """Link this protocol against ``table``, filling its blank event slots."""
        missing = [e.__name__ for e in cls.required_events if e not in table.events]
        missing += [c.__name__ for c in cls.required_commands if c not in table.commands]
        if missing:
            raise RuntimeError(
                f"Cannot link {cls.__name__}: undefined symbols [{', '.join(sorted(missing))}]"
            )

        instance = cls()
        instance._table = table
        for member in vars(cls).values():
            if event := getattr(member, "required_event", None):
                table.events[event] = member.__get__(instance, cls)
        return instance


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

class Start(Event):
    pass


@dataclass
class Telemetry(Event):
    x: float
    y: float
    z: float


class Stop(Event):
    pass


@dataclass
class Move(Command):
    x: float
    y: float
    z: float


@dataclass
class Broadcast(Command):
    payload: str


class Land(Command):
    pass


class SweepProtocol(Protocol):
    move = command(Move)
    broadcast = command(Broadcast)

    @subscribe(Start)
    def on_start(self, event: Start) -> None:
        self.move(10.0, 20.0, 30.0)

    @subscribe(Telemetry)
    def on_telemetry(self, event: Telemetry) -> None:
        self.broadcast(f"at ({event.x}, {event.y}, {event.z})")


class GreedyProtocol(SweepProtocol):
    land = command(Land)  # the demo table below does not provide Land


if __name__ == "__main__":
    # The environment (embedded firmware or simulator node) builds its table:
    # blank event slots plus the command implementations it already has.
    table = LinkTable(
        events={Start: None, Telemetry: None, Stop: None},
        commands={
            Move: lambda cmd: print(f"[motors] {cmd}"),
            Broadcast: lambda cmd: print(f"[radio]  {cmd}"),
        },
    )

    SweepProtocol.bind(table)

    # The environment drives the loop by calling the linked slots directly.
    if handler := table.events[Start]:
        handler(Start())
    if handler := table.events[Telemetry]:
        handler(Telemetry(1.0, 2.0, 3.0))
    print(f"[unlinked] Stop slot is still blank: {table.events[Stop]}")

    try:
        GreedyProtocol.bind(table)
    except RuntimeError as error:
        print(f"[expected] {error}")
