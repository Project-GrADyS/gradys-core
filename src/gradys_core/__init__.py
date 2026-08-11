"""gradys-core: the protocol interface shared by GrADyS-SIM NextGen and gradys-embedded.

A protocol is a pure reactor: it **sends commands** and **subscribes to events**. It
never implements a command and never publishes an event — each execution environment
supplies the implementations and drives the deliveries.

Both sets are declared as generic parameters, and using anything outside them is a type
error::

    from gradys_core import (
        Protocol, subscribe, PRIORITY_PROTOCOL,
        StartEvent, TelemetryEvent, GotoCoords, ScheduleTimer,
    )

    Events   = StartEvent | TelemetryEvent
    Commands = GotoCoords | ScheduleTimer

    class Circler(Protocol[Events, Commands]):
        def on_bind(self) -> None:
            subscribe(self.provider, StartEvent, self._on_start, PRIORITY_PROTOCOL)

        def _on_start(self, e: StartEvent) -> None:
            self.provider.send(GotoCoords(0.0, 0.0, 30.0))
            self.provider.send(ScheduleTimer("lap", 10.0))

``Protocol`` shadows ``typing.Protocol``; import ``ProtocolBase`` instead in modules that
need both.
"""

from gradys_core.bus import (
    PRIORITY_OBSERVER,
    PRIORITY_PLUGIN,
    PRIORITY_PROTOCOL,
    Disposition,
    EventBus,
    HandlerResult,
    Subscription,
)
from gradys_core.commands import (
    Broadcast,
    CancelTimer,
    Command,
    CommunicationCommand,
    GotoCoords,
    GotoGeoCoords,
    MobilityCommand,
    ScheduleTimer,
    SendMessage,
    SetSpeed,
    TrackVariable,
)
from gradys_core.events import (
    Event,
    PacketEvent,
    StartEvent,
    StopEvent,
    TelemetryEvent,
    TimerEvent,
)
from gradys_core.geometry import (
    GeoPosition,
    Position,
    cartesian_to_geo,
    distance,
    geo_to_cartesian,
    squared_distance,
)
from gradys_core.host import (
    Binding,
    CommandRegistry,
    bind,
    check_capabilities,
    declared_commands,
    declared_events,
)
from gradys_core.protocol import (
    NotInstalledError,
    Protocol,
    ProtocolBase,
    Provider,
    SupportsCheck,
    UndeclaredEventError,
    UnsupportedCommandError,
    subscribe,
    supports_command,
)

__version__ = "0.1.0"

__all__ = [
    # protocol
    "Protocol",
    "ProtocolBase",
    "Provider",
    "subscribe",
    "Subscription",
    "Disposition",
    "HandlerResult",
    "PRIORITY_OBSERVER",
    "PRIORITY_PLUGIN",
    "PRIORITY_PROTOCOL",
    # events
    "Event",
    "StartEvent",
    "StopEvent",
    "TelemetryEvent",
    "PacketEvent",
    "TimerEvent",
    # commands
    "Command",
    "MobilityCommand",
    "CommunicationCommand",
    "GotoCoords",
    "GotoGeoCoords",
    "SetSpeed",
    "SendMessage",
    "Broadcast",
    "ScheduleTimer",
    "CancelTimer",
    "TrackVariable",
    # environment seam
    "bind",
    "Binding",
    "check_capabilities",
    "SupportsCheck",
    "supports_command",
    "CommandRegistry",
    "declared_events",
    "declared_commands",
    "UnsupportedCommandError",
    "UndeclaredEventError",
    "NotInstalledError",
    # geometry
    "Position",
    "GeoPosition",
    "geo_to_cartesian",
    "cartesian_to_geo",
    "squared_distance",
    "distance",
    # internals exposed for hosts
    "EventBus",
    "__version__",
]
