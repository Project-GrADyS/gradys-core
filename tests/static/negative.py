"""Uses outside the declared sets. Every one MUST be a type error.

Run with ``mypy --strict --warn-unused-ignores``: the pass condition is zero output.
An error that stops firing shows up as an unused ignore; an unexpected error shows up
directly. Pyright is run with ``reportUnnecessaryTypeIgnoreComment = "error"``, which
gives the same property. The guarantee cannot quietly become vacuous.

The guarantees under test (same numbering as positive.py and tests/README.md), with
the mypy error code each violation must produce:

    G1  event-set membership    subscribe() with an undeclared event      [misc]
                                (mypy's message is the unhelpful "Cannot infer value
                                of type parameter _E" — that IS the membership failure;
                                pyright's message for the same case is precise, and the
                                runtime backstop raises UndeclaredEventError)
    G2  handler consistency     handler cannot accept the event           [arg-type]
    G3  command-set membership  provider.send() of an undeclared command  [arg-type]
    G4  plugin capability       protocol lacks what the plugin requires   [arg-type]
    G5  subtype asymmetry       subscribing to a SUPERtype of a declared
                                event (declared TelemetryEvent does not
                                entitle you to every Event)               [misc]
"""

from __future__ import annotations

from typing import Optional

from gradys_core import (
    Broadcast,
    CancelTimer,
    Disposition,
    Event,
    GotoCoords,
    GotoGeoCoords,
    PacketEvent,
    Protocol,
    Provider,
    ScheduleTimer,
    SetSpeed,
    StartEvent,
    StopEvent,
    TelemetryEvent,
    TimerEvent,
    TrackVariable,
    subscribe,
)

Events = TelemetryEvent | PacketEvent
Commands = GotoCoords | Broadcast | ScheduleTimer


class Narrow(Protocol[Events, Commands]):
    def bad_subscriptions(self) -> None:
        # G1: TimerEvent is not in the declared event set
        subscribe(self.provider, TimerEvent, self._on_timer)  # type: ignore[misc]
        # G1: ...same, via a lambda
        subscribe(self.provider, StartEvent, lambda e: None)  # type: ignore[misc]
        # G1: ...same, at an explicit priority
        subscribe(self.provider, StopEvent, self._on_stop, 0)  # type: ignore[misc]
        # G5: Event is a SUPERtype of the declared events, not a member or subtype
        subscribe(self.provider, Event, lambda e: None)  # type: ignore[misc]
        # G2: declared event, but a handler for a different declared event
        subscribe(self.provider, TelemetryEvent, self._on_packet)  # type: ignore[arg-type]
        # G2: declared event, but a handler for an undeclared event
        subscribe(self.provider, PacketEvent, self._on_timer)  # type: ignore[arg-type]

    def bad_commands(self) -> None:
        # G3: none of these are in the declared command set
        self.provider.send(SetSpeed(1.0))  # type: ignore[arg-type]
        self.provider.send(CancelTimer("tick"))  # type: ignore[arg-type]
        self.provider.send(GotoGeoCoords(0.0, 0.0, 0.0))  # type: ignore[arg-type]
        self.provider.send(TrackVariable("x", 1))  # type: ignore[arg-type]

    def good(self) -> None:
        """None of these may error."""
        subscribe(self.provider, TelemetryEvent, self._on_telemetry)
        subscribe(self.provider, PacketEvent, self._on_packet)
        subscribe(self.provider, PacketEvent, lambda e: None)
        self.provider.send(GotoCoords(0.0, 0.0, 0.0))
        self.provider.send(Broadcast("hi"))
        self.provider.send(ScheduleTimer("tick", 1.0))

    def _on_telemetry(self, e: TelemetryEvent) -> Optional[Disposition]:
        return None

    def _on_packet(self, e: PacketEvent) -> Optional[Disposition]:
        return None

    def _on_timer(self, e: TimerEvent) -> Optional[Disposition]:
        return None

    def _on_stop(self, e: StopEvent) -> Optional[Disposition]:
        return None


class NeedsBoth:
    """G4: a plugin requiring an event and two commands, on its Provider parameter."""

    def __init__(
        self, provider: Provider[TimerEvent, GotoCoords | ScheduleTimer]
    ) -> None:
        self._provider = provider

    def bad_plugin_body(self) -> None:
        # G1 for plugin bodies: outside the plugin's OWN declared contract
        subscribe(self._provider, TelemetryEvent, lambda e: None)  # type: ignore[misc]
        # G3 for plugin bodies
        self._provider.send(Broadcast("hi"))  # type: ignore[arg-type]


class MissingEvent(Protocol[TelemetryEvent, GotoCoords | ScheduleTimer]):
    """Has the commands, lacks TimerEvent."""


class MissingCommand(Protocol[TelemetryEvent | TimerEvent, GotoCoords]):
    """Has the events, lacks ScheduleTimer."""


class HasBoth(Protocol[TelemetryEvent | TimerEvent, GotoCoords | ScheduleTimer | Broadcast]):
    """Superset of everything the plugin needs."""


def plugin_requirements(
    missing_event: MissingEvent, missing_command: MissingCommand, has_both: HasBoth
) -> None:
    # G4: each missing capability is an error at the wiring site
    NeedsBoth(missing_event.provider)  # type: ignore[arg-type]
    NeedsBoth(missing_command.provider)  # type: ignore[arg-type]
    NeedsBoth(has_both.provider)  # must NOT error
