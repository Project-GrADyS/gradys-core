"""Draft 1 — decorator subscribe + a Host object.

Authoring surface: protocols mark handlers with ``@subscribe(Event)`` and declare
outgoing commands as ``attr = command(CommandType)`` class attributes; requirements
are collected automatically by ``__init_subclass__``.

Environment surface: a ``Host`` with exactly three methods —

    host.register_listener(CommandType, fn)  # environment provides command executors
    host.bind(UserProtocolSubclass)          # capability check + wiring
    host.deliver(event)                      # push an event into the bound protocol

gradys-embedded and gradys-sim NG would each construct a Host, register listeners
for the commands they can execute (motors, radio / physics engine), then bind.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any


class Event:
    pass


class Command:
    pass


# ---------------------------------------------------------------------------
# Authoring helpers
# ---------------------------------------------------------------------------

def subscribe(event: type[Event]) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark a method as the handler for ``event``; collected at class creation."""

    def decorate(method: Callable[..., Any]) -> Callable[..., Any]:
        setattr(method, "required_event", event)
        return method

    return decorate


def command(command_type: type[Command]) -> Callable[..., None]:
    """Declare an outgoing command as a class attribute.

    ``self.move(...)`` builds ``Move(...)`` and forwards it to the host, which
    routes it to whatever listener the environment registered for ``Move``.
    """

    def send(self: "Protocol", *args: Any, **kwargs: Any) -> None:
        self._host._dispatch(command_type(*args, **kwargs))

    send.required_command = command_type  # type: ignore[attr-defined]
    return send


class Protocol:
    """Base class: requirements are derived from usage sites, never declared."""

    required_events: set[type[Event]] = set()
    required_commands: set[type[Command]] = set()
    _host: "Host"

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


# ---------------------------------------------------------------------------
# Host
# ---------------------------------------------------------------------------

class Host:
    """One host per node. Owns the listener table and the bound protocol."""

    def __init__(self, supported_events: Iterable[type[Event]]) -> None:
        self._supported_events = set(supported_events)
        self._listeners: dict[type[Command], Callable[[Command], None]] = {}
        self._handlers: dict[type[Event], Callable[[Event], None]] = {}
        self._protocol: Protocol | None = None

    def register_listener(
        self, command_type: type[Command], fn: Callable[[Command], None]
    ) -> None:
        """Environment side: 'when the protocol issues this command, run fn'."""
        self._listeners[command_type] = fn

    def bind(self, protocol_cls: type[Protocol]) -> Protocol:
        """Check the protocol's requirements against this host's capabilities."""
        missing_events = protocol_cls.required_events - self._supported_events
        missing_commands = protocol_cls.required_commands - set(self._listeners)
        if missing_events or missing_commands:
            raise RuntimeError(
                f"Cannot bind {protocol_cls.__name__}: "
                f"missing events [{_names(missing_events)}]; "
                f"missing commands [{_names(missing_commands)}]"
            )

        instance = protocol_cls()
        instance._host = self
        for member in vars(protocol_cls).values():
            if event := getattr(member, "required_event", None):
                self._handlers[event] = member.__get__(instance, protocol_cls)
        self._protocol = instance
        return instance

    def deliver(self, event: Event) -> None:
        """Push an event into the bound protocol (no-op if it never subscribed)."""
        if self._protocol is None:
            raise RuntimeError("deliver() before bind()")
        if handler := self._handlers.get(type(event)):
            handler(event)

    def _dispatch(self, cmd: Command) -> None:
        self._listeners[type(cmd)](cmd)


def _names(items: Iterable[type[Any]]) -> str:
    return ", ".join(sorted(item.__name__ for item in items)) or "none"


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
    land = command(Land)  # no host in this demo registers a Land listener


if __name__ == "__main__":
    host = Host(supported_events={Start, Telemetry})
    host.register_listener(Move, lambda cmd: print(f"[motors] {cmd}"))
    host.register_listener(Broadcast, lambda cmd: print(f"[radio]  {cmd}"))

    host.bind(SweepProtocol)
    host.deliver(Start())
    host.deliver(Telemetry(1.0, 2.0, 3.0))

    try:
        host.bind(GreedyProtocol)
    except RuntimeError as error:
        print(f"[expected] {error}")
