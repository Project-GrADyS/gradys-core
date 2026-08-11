"""Running unmodified old-style protocols on a new runtime.

This module re-declares the legacy ``IProtocol`` / ``IProvider`` contract byte-compatibly
so existing code keeps importing and type-checking, and provides
:class:`LegacyProtocolAdapter`, which presents an old protocol to a new runtime.

Only this direction is supported. A new-style protocol does **not** run on the old
simulator, old plugins are not guaranteed to work, and the OMNeT++ consequence model is
not preserved.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar, Dict, Optional, Type

from gradys_core.bus import PRIORITY_PROTOCOL, Disposition
from gradys_core.commands import (
    Broadcast,
    CancelTimer,
    GotoCoords,
    GotoGeoCoords,
    ScheduleTimer,
    SendMessage,
    SetSpeed,
    TrackVariable,
)
from gradys_core.events import (
    PacketEvent,
    StartEvent,
    StopEvent,
    TelemetryEvent,
    TimerEvent,
)
from gradys_core.geometry import Position
from gradys_core.protocol import Protocol, subscribe

# --------------------------------------------------------------------------- legacy types


@dataclass
class Telemetry:
    """Legacy telemetry message. One field, as it always had."""

    current_position: Position


class MobilityCommandType(int, Enum):
    GOTO_COORDS = 1
    GOTO_GEO_COORDS = 2
    SET_SPEED = 3


@dataclass
class MobilityCommand:
    """Legacy mobility command: an enum tag plus six positional floats."""

    command_type: MobilityCommandType
    param_1: float = 0
    param_2: float = 0
    param_3: float = 0
    param_4: float = 0
    param_5: float = 0
    param_6: float = 0


class GotoCoordsMobilityCommand(MobilityCommand):
    def __init__(self, x: float, y: float, z: float) -> None:
        super().__init__(MobilityCommandType.GOTO_COORDS, x, y, z)


class GotoGeoCoordsMobilityCommand(MobilityCommand):
    def __init__(self, lat: float, lon: float, alt: float) -> None:
        super().__init__(MobilityCommandType.GOTO_GEO_COORDS, lat, lon, alt)


class SetSpeedMobilityCommand(MobilityCommand):
    def __init__(self, speed: float) -> None:
        super().__init__(MobilityCommandType.SET_SPEED, speed)


class CommunicationCommandType(int, Enum):
    SEND = 0
    BROADCAST = 1


@dataclass
class CommunicationCommand:
    command_type: CommunicationCommandType
    message: str
    destination: Optional[int] = None


class SendMessageCommand(CommunicationCommand):
    def __init__(self, message: str, destination: Optional[int] = None) -> None:
        # The original assigned attributes directly without calling super().__init__,
        # which left `destination` unset on the instance and broke dataclass equality.
        super().__init__(CommunicationCommandType.SEND, message, destination)


class BroadcastMessageCommand(CommunicationCommand):
    def __init__(self, message: str) -> None:
        super().__init__(CommunicationCommandType.BROADCAST, message, None)


class IProvider(ABC):
    """Legacy provider interface, unchanged."""

    tracked_variables: Dict[str, Any]

    @abstractmethod
    def send_communication_command(self, command: CommunicationCommand) -> None: ...

    @abstractmethod
    def send_mobility_command(self, command: MobilityCommand) -> None: ...

    @abstractmethod
    def schedule_timer(self, timer: str, timestamp: float) -> None: ...

    @abstractmethod
    def cancel_timer(self, timer: str) -> None: ...

    @abstractmethod
    def current_time(self) -> float: ...

    @abstractmethod
    def get_id(self) -> int: ...


class IProtocol(ABC):
    """Legacy protocol interface, unchanged.

    Wrap a subclass with :func:`legacy` to :func:`~gradys_core.bind` it to a new
    environment.
    """

    provider: IProvider

    @classmethod
    def instantiate(cls, provider: IProvider) -> "IProtocol":
        protocol = cls()
        protocol.provider = provider
        return protocol

    @abstractmethod
    def initialize(self) -> None: ...

    @abstractmethod
    def handle_timer(self, timer: str) -> None: ...

    @abstractmethod
    def handle_packet(self, message: str) -> None: ...

    @abstractmethod
    def handle_telemetry(self, telemetry: Telemetry) -> None: ...

    @abstractmethod
    def finish(self) -> None: ...


# --------------------------------------------------------------------------- adapter

LegacyEvents = StartEvent | StopEvent | TimerEvent | PacketEvent | TelemetryEvent
LegacyCommands = (
    GotoCoords
    | GotoGeoCoords
    | SetSpeed
    | SendMessage
    | Broadcast
    | ScheduleTimer
    | CancelTimer
    | TrackVariable
)


class _TrackedVariables(Dict[str, Any]):
    """A dict whose writes become ``TrackVariable`` commands.

    Same trick the simulator's ``interop.py`` already used internally, which is what
    made ``tracked_variables`` an action in disguise in the first place.
    """

    def __init__(self, adapter: "LegacyProtocolAdapter") -> None:
        super().__init__()
        self._adapter = adapter

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        self._adapter.provider.send(TrackVariable(key, value))


class _LegacyProviderShim(IProvider):
    """Turns the four legacy provider calls into new-world commands.

    Everything routes through the adapter's ``provider``, so legacy protocols are
    subject to the same capability check and command path as native ones.
    """

    def __init__(self, adapter: "LegacyProtocolAdapter") -> None:
        self._adapter = adapter
        self.tracked_variables = _TrackedVariables(adapter)

    def send_mobility_command(self, command: MobilityCommand) -> None:
        send = self._adapter.provider.send
        if command.command_type == MobilityCommandType.GOTO_COORDS:
            send(GotoCoords(command.param_1, command.param_2, command.param_3))
        elif command.command_type == MobilityCommandType.GOTO_GEO_COORDS:
            send(GotoGeoCoords(command.param_1, command.param_2, command.param_3))
        elif command.command_type == MobilityCommandType.SET_SPEED:
            send(SetSpeed(command.param_1))
        else:
            raise ValueError(f"Unknown mobility command type: {command.command_type!r}")

    def send_communication_command(self, command: CommunicationCommand) -> None:
        if command.command_type == CommunicationCommandType.SEND:
            if command.destination is None:
                raise ValueError("SEND command requires a destination")
            self._adapter.provider.send(SendMessage(command.message, command.destination))
        elif command.command_type == CommunicationCommandType.BROADCAST:
            self._adapter.provider.send(Broadcast(command.message))
        else:
            raise ValueError(f"Unknown communication command type: {command.command_type!r}")

    def schedule_timer(self, timer: str, timestamp: float) -> None:
        # Legacy timestamps are absolute; ScheduleTimer.delay is relative.
        self._adapter.provider.send(ScheduleTimer(timer, timestamp - self.current_time()))

    def cancel_timer(self, timer: str) -> None:
        self._adapter.provider.send(CancelTimer(timer))

    def current_time(self) -> float:
        return self._adapter.provider.now()

    def get_id(self) -> int:
        return self._adapter.provider.node_id()


class LegacyProtocolAdapter(Protocol[LegacyEvents, LegacyCommands]):
    """Presents an unmodified :class:`IProtocol` subclass to a new runtime.

    Build one with :func:`legacy`, then install it like any other protocol::

        bind(legacy(MyOldProtocol), provider=..., send=..., supports=...)
    """

    legacy_class: ClassVar[Type[IProtocol]]

    def __init__(self) -> None:
        # Plain __init__ -- the Protocol base is stateless, there is no super() to call.
        self.shim = _LegacyProviderShim(self)
        # instantiate(), not __init__ -- subclasses are allowed to override it.
        self.legacy_protocol = self.legacy_class.instantiate(self.shim)

    def on_bind(self) -> None:
        subscribe(self.provider, StartEvent, self._on_start, PRIORITY_PROTOCOL)
        subscribe(self.provider, TimerEvent, self._on_timer, PRIORITY_PROTOCOL)
        subscribe(self.provider, PacketEvent, self._on_packet, PRIORITY_PROTOCOL)
        subscribe(self.provider, TelemetryEvent, self._on_telemetry, PRIORITY_PROTOCOL)
        subscribe(self.provider, StopEvent, self._on_stop, PRIORITY_PROTOCOL)

    @property
    def tracked_variables(self) -> Dict[str, Any]:
        return self.shim.tracked_variables

    def _on_start(self, event: StartEvent) -> Optional[Disposition]:
        self.legacy_protocol.initialize()
        return None

    def _on_timer(self, event: TimerEvent) -> Optional[Disposition]:
        self.legacy_protocol.handle_timer(event.tag)
        return None

    def _on_packet(self, event: PacketEvent) -> Optional[Disposition]:
        # event.source is dropped: the legacy signature has nowhere to put it. This is
        # the fidelity the adapter promises, and the reason to migrate off it.
        self.legacy_protocol.handle_packet(event.payload)
        return None

    def _on_telemetry(self, event: TelemetryEvent) -> Optional[Disposition]:
        self.legacy_protocol.handle_telemetry(Telemetry(event.position))
        return None

    def _on_stop(self, event: StopEvent) -> Optional[Disposition]:
        self.legacy_protocol.finish()
        return None


_adapters: Dict[Type[IProtocol], Type[LegacyProtocolAdapter]] = {}


def legacy(cls: Type[IProtocol]) -> Type[LegacyProtocolAdapter]:
    """Wrap an old-style protocol class so :func:`~gradys_core.bind` can install it.

    Idempotent per class, so repeated calls return the same adapter type and
    ``declared_commands`` stays stable.
    """
    adapter = _adapters.get(cls)
    if adapter is None:
        adapter = type(
            f"Legacy_{cls.__name__}",
            (LegacyProtocolAdapter,),
            {"legacy_class": cls, "__doc__": f"Adapter around legacy {cls.__name__}."},
        )
        _adapters[cls] = adapter
    return adapter


def is_legacy(cls: type) -> bool:
    """True if ``cls`` is an old-style protocol needing :func:`legacy`."""
    return issubclass(cls, IProtocol)


__all__ = [
    "BroadcastMessageCommand",
    "CommunicationCommand",
    "CommunicationCommandType",
    "GotoCoordsMobilityCommand",
    "GotoGeoCoordsMobilityCommand",
    "IProtocol",
    "IProvider",
    "LegacyCommands",
    "LegacyEvents",
    "LegacyProtocolAdapter",
    "MobilityCommand",
    "MobilityCommandType",
    "SendMessageCommand",
    "SetSpeedMobilityCommand",
    "Telemetry",
    "is_legacy",
    "legacy",
]
