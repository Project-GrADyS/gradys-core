"""Correct usage. Must produce ZERO diagnostics from mypy and pyright.

Anything flagged here is a false positive in the encoding: the guarantee would be
rejecting legitimate code.

The guarantees under test (the same numbering as negative.py and tests/README.md):

    G1  event-set membership   subscribe() only accepts events in the declared set
    G2  handler consistency    the handler's parameter must accept the subscribed event
    G3  command-set membership provider.send() only accepts declared commands
    G4  plugin capability      a Provider[...] parameter states requirements; any
                               protocol whose declared sets are SUPERSETS is accepted
    G5  subtype asymmetry      you may subscribe to a declared type or a SUBtype of it,
                               never a supertype; a catch-all declares Event itself

This file proves each guarantee admits the legitimate cases; negative.py proves each
rejects the violations. Also exercised here: the no-super rule (protocols define plain
__init__ or none at all — the base is stateless).
"""

from __future__ import annotations

from typing import Optional, Union

from gradys_core import (
    PRIORITY_OBSERVER,
    PRIORITY_PLUGIN,
    PRIORITY_PROTOCOL,
    Binding,
    Broadcast,
    CancelTimer,
    Command,
    CommandRegistry,
    Disposition,
    Event,
    GotoCoords,
    MobilityCommand,
    PacketEvent,
    Protocol,
    Provider,
    ScheduleTimer,
    SetSpeed,
    StartEvent,
    StopEvent,
    Subscription,
    TelemetryEvent,
    TimerEvent,
    bind,
    subscribe,
)

SweepEvents = StartEvent | StopEvent | TelemetryEvent | PacketEvent | TimerEvent
SweepCommands = GotoCoords | Broadcast | SetSpeed | ScheduleTimer | CancelTimer


class SweepProtocol(Protocol[SweepEvents, SweepCommands]):
    """G1/G2/G3: the full authoring pattern, all inside the declared sets."""

    def __init__(self) -> None:  # plain initializer, NO super().__init__()
        self.laps = 0

    def on_bind(self) -> None:
        # G1: exact member of the declared set
        subscribe(self.provider, TelemetryEvent, self._on_telemetry, PRIORITY_PROTOCOL)
        # explicit priority, and a default-priority call
        subscribe(self.provider, TimerEvent, self._on_timer, PRIORITY_PROTOCOL)
        subscribe(self.provider, PacketEvent, self._on_packet)
        # G2: lambda handler
        subscribe(self.provider, StartEvent, lambda e: None)
        # G2: handler annotated WIDER than the subscribed event (contravariance)
        subscribe(self.provider, StopEvent, self._on_any)

    def _on_telemetry(self, e: TelemetryEvent) -> Optional[Disposition]:
        x, y, z = e.position
        # G3: every declared command family member
        self.provider.send(GotoCoords(x, y, z + 10.0))
        self.provider.send(SetSpeed(5.0))
        self.provider.send(ScheduleTimer("lap", 10.0))
        self.provider.send(CancelTimer("lap"))
        self.provider.send(Broadcast(f"at {e.timestamp}"))
        return None

    def _on_timer(self, e: TimerEvent) -> Optional[Disposition]:
        if e.tag == "lap":
            self.laps += 1
            self.provider.send(ScheduleTimer("lap", 10.0))
        return Disposition.CONTINUE

    def _on_packet(self, e: PacketEvent) -> Optional[Disposition]:
        peer: int = e.source  # source is typed and present
        body: str = e.payload
        del peer, body
        return Disposition.STOP

    def _on_any(self, e: Union[StopEvent, TelemetryEvent]) -> None:
        return None


class SensorEvent(Event):
    """A user-defined event hierarchy."""


class Overheated(SensorEvent):
    pass


class Undervolted(SensorEvent):
    pass


class HierarchyProtocol(Protocol[SensorEvent, GotoCoords]):
    """G5: declaring a base event admits its subclasses (subtype-yes half)."""

    def on_bind(self) -> None:
        subscribe(self.provider, SensorEvent, self._on_any_sensor, PRIORITY_OBSERVER)
        subscribe(self.provider, Overheated, self._on_overheat, PRIORITY_PROTOCOL)

    def _on_any_sensor(self, e: SensorEvent) -> Disposition:
        return Disposition.CONTINUE

    def _on_overheat(self, e: Overheated) -> None:
        self.provider.send(GotoCoords(0.0, 0.0, 0.0))


class CatchAll(Protocol[Event, GotoCoords]):
    """G5: declaring ``Event`` itself is the explicit opt-in to receiving anything."""

    def on_bind(self) -> None:
        subscribe(self.provider, Event, self._anything, PRIORITY_OBSERVER)
        subscribe(self.provider, TelemetryEvent, self._telemetry, PRIORITY_PROTOCOL)

    def _anything(self, e: Event) -> Disposition:
        return Disposition.CONTINUE

    def _telemetry(self, e: TelemetryEvent) -> None:
        return None


class MissionPlugin:
    """G4: a plugin declares only what it needs, on its Provider parameter."""

    def __init__(self, provider: Provider[TelemetryEvent, GotoCoords | SetSpeed]) -> None:
        self._provider = provider
        # G1 for plugin bodies: checked against the plugin's OWN declared contract
        self._sub: Subscription = subscribe(
            provider, TelemetryEvent, self._on_telemetry, PRIORITY_PLUGIN
        )

    def _on_telemetry(self, e: TelemetryEvent) -> Optional[Disposition]:
        self._provider.send(GotoCoords(*e.position))
        return Disposition.CONTINUE

    def stop(self) -> None:
        self._sub.cancel()


def wire(protocol: SweepProtocol) -> None:
    # G4: SweepProtocol's sets are supersets of what the plugin requires
    MissionPlugin(protocol.provider)


class FamilyProtocol(Protocol[TelemetryEvent, MobilityCommand]):
    """G3: declaring a command family accepts any member of it."""

    def on_bind(self) -> None:
        subscribe(self.provider, TelemetryEvent, self._on_telemetry)

    def _on_telemetry(self, e: TelemetryEvent) -> None:
        self.provider.send(GotoCoords(0.0, 0.0, 0.0))
        self.provider.send(SetSpeed(1.0))


# ------------------------------------------------------------- the environment seam


def execute(command: Command) -> None:
    return None


def supports_everything(command: type) -> bool:
    return True


def wire_environment() -> None:
    """bind() takes an environment-built Provider and returns a *typed* binding."""
    provider: Provider[SweepEvents, SweepCommands] = Provider(
        node_id=1, now=lambda: 0.0, send=execute, supports=supports_everything
    )
    binding: Binding[SweepProtocol] = bind(SweepProtocol, provider)
    # .protocol is the concrete class, not Any: its declared sets still apply.
    protocol: SweepProtocol = binding.protocol
    protocol.provider.send(GotoCoords(0.0, 0.0, 0.0))
    subscribe(protocol.provider, TelemetryEvent, lambda e: None)
    binding.start()
    binding.deliver(StartEvent())
    binding.stop("done")

    # a CommandRegistry supplies callables with exactly the right shapes
    registry = CommandRegistry()
    registry.add(MobilityCommand, execute)
    bind(
        FamilyProtocol,
        Provider(node_id=2, now=lambda: 0.0, send=registry.dispatch, supports=registry.supports),
    )
