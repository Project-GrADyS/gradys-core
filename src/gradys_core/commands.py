"""Commands: everything a protocol asks the execution environment to do.

A protocol never implements a command. It declares the ones it needs and sends them;
each environment registers a handler for every command it supports. Timers, mobility
and communication are all ordinary commands here — none is privileged by the core, and
a user-defined :class:`Command` subclass is wired up exactly the same way.

Commands are frozen dataclasses so they stay safe to hand across the embedded runtime's
fire-and-forget async boundary, and so equality works for tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class Command:
    """Base class for every command.

    Commands are fire-and-forget: they return nothing, and failure is reported (if at
    all) as an event. Anything that needs to return a value synchronously belongs on
    :class:`~gradys_core.protocol.Provider` instead.
    """

    __slots__ = ()


class MobilityCommand(Command):
    """Marker base for commands that move the node.

    An environment may register a handler against this base rather than each concrete
    subclass; ``CommandRegistry`` resolves through the MRO.
    """

    __slots__ = ()


class CommunicationCommand(Command):
    """Marker base for commands that send data to other nodes."""

    __slots__ = ()


@dataclass(frozen=True)
class GotoCoords(MobilityCommand):
    """Move to a point in the local cartesian frame, in metres."""

    x: float
    y: float
    z: float


@dataclass(frozen=True)
class GotoGeoCoords(MobilityCommand):
    """Move to a geographic point."""

    lat: float
    lon: float
    alt: float


@dataclass(frozen=True)
class SetSpeed(MobilityCommand):
    """Set the node's travel speed, in m/s."""

    speed: float


@dataclass(frozen=True)
class SendMessage(CommunicationCommand):
    """Send a message to one node."""

    payload: str
    destination: int


@dataclass(frozen=True)
class Broadcast(CommunicationCommand):
    """Send a message to every reachable node."""

    payload: str


@dataclass(frozen=True)
class ScheduleTimer(Command):
    """Ask for a :class:`~gradys_core.events.TimerEvent` after ``delay`` seconds.

    ``delay`` is **relative**, deliberately. The two runtimes disagree on clock epoch —
    the simulator counts from zero, the embedded runner uses ``loop.time()`` — and a
    relative delay keeps that disagreement out of protocol code entirely.

    Scheduling with a non-positive delay is legal and fires at the next opportunity; it
    never raises.
    """

    tag: str
    delay: float


@dataclass(frozen=True)
class CancelTimer(Command):
    """Cancel **every** pending timer carrying ``tag``.

    Cancel-all is the semantics ``IProvider.cancel_timer`` always documented and the
    simulator always implemented. Timers have no handle, so the tag is the only thing
    there is to cancel by; a protocol needing finer control encodes uniqueness in the tag.
    """

    tag: str


@dataclass(frozen=True)
class TrackVariable(Command):
    """Report a named value to whatever instrumentation the environment provides.

    Replaces the legacy ``IProvider.tracked_variables`` dict. A mutable dict whose
    ``__setitem__`` had side effects was an action wearing a data structure's clothing;
    as a command it goes through the same registry and capability check as everything else.
    """

    name: str
    value: Any
