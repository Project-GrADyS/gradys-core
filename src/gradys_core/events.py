"""Events: everything the execution environment tells a protocol about.

A protocol never publishes an event. It subscribes to the ones it declared, and the
environment delivers them. The built-ins below are the common vocabulary; they carry
no privileged status in the core, and user-defined subclasses of :class:`Event` are
handled by exactly the same machinery.
"""

from __future__ import annotations

from dataclasses import dataclass

from gradys_core.geometry import Position


class Event:
    """Base class for every event.

    Subclass freely to add new notifications to the framework. An environment
    publishes them through ``Binding.deliver``; a protocol receives them by declaring
    the type in its event set and calling :func:`gradys_core.subscribe`.

    Subclasses are conventionally frozen dataclasses: an event is a fact that already
    happened, so it should not be mutable, and handlers further down the chain must
    see what the ones before them saw.
    """

    __slots__ = ()


class StartEvent(Event):
    """Delivered once, before any other event.

    Successor to ``IProtocol.initialize()``. Environments deliver this to every node in
    arbitrary order, so do not assume another node has started.

    Handlers for this event always all run: a ``Disposition.STOP`` is ignored, so one
    plugin cannot prevent another from initialising.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "StartEvent()"


@dataclass(frozen=True)
class StopEvent(Event):
    """Delivered once, last. Successor to ``IProtocol.finish()``.

    As with :class:`StartEvent`, ``Disposition.STOP`` is ignored so that one plugin
    cannot skip another's teardown.
    """

    reason: str = "shutdown"


@dataclass(frozen=True)
class TelemetryEvent(Event):
    """The node's own mobility state.

    Attributes:
        position: where the node was when the sample was taken.
        timestamp: the node's own clock (the same reference as ``provider.now()``) at
            *sample* time, which is not delivery time. The embedded runtime polls
            telemetry (0.5 s by default), so a sample can be meaningfully stale by the
            time a handler sees it. Like every ``now()`` value, it is never comparable
            across nodes.
    """

    position: Position
    timestamp: float


@dataclass(frozen=True)
class PacketEvent(Event):
    """A message received from another node.

    Attributes:
        payload: the message body. Serialization is the protocol's business.
        source: id of the node that sent it.

    ``source`` is the one addition to the legacy contract. The old
    ``handle_packet(message: str)`` dropped it even though every transport already
    carried it, which is why protocols hand-rolled a sender field into their JSON.
    """

    payload: str
    source: int


@dataclass(frozen=True)
class TimerEvent(Event):
    """A timer previously requested with ``ScheduleTimer`` has fired.

    Attributes:
        tag: the tag the timer was scheduled with. Timers carry no handle — a command
            is fire-and-forget and cannot return one — so the tag is the only identity
            a timer has. Protocols needing uniqueness encode it in the tag.
    """

    tag: str
