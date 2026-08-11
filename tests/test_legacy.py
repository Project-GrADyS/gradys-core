"""Contract under test: legacy emulation — an unmodified ``IProtocol`` runs unchanged.

The adapter's promised fidelity, which explains the otherwise-odd assertions below:
the four legacy provider calls become commands (subject to the same capability gate as
native protocols), absolute ``schedule_timer`` timestamps become relative delays,
``tracked_variables`` writes become ``TrackVariable`` commands, and
``PacketEvent.source`` is **dropped** — ``handle_packet(message: str)`` has nowhere to
put it, and recovering the sender is the stated reason to migrate off the adapter.
"""

from __future__ import annotations

from typing import List

import pytest

from gradys_core import (
    Broadcast,
    CancelTimer,
    GotoCoords,
    ScheduleTimer,
    SendMessage,
    SetSpeed,
    TrackVariable,
    UnsupportedCommandError,
    declared_commands,
)
from gradys_core.legacy import (
    BroadcastMessageCommand,
    GotoCoordsMobilityCommand,
    GotoGeoCoordsMobilityCommand,
    IProtocol,
    LegacyProtocolAdapter,
    SendMessageCommand,
    SetSpeedMobilityCommand,
    Telemetry,
    is_legacy,
    legacy,
)
from gradys_core.testing import FakeHost, install


class OldStyleProtocol(IProtocol):
    """Written against the legacy interface. Not modified in any way."""

    def initialize(self) -> None:
        self.log: List[str] = []
        self.provider.tracked_variables["state"] = "up"
        self.provider.send_mobility_command(SetSpeedMobilityCommand(5.0))
        self.provider.send_mobility_command(GotoCoordsMobilityCommand(1.0, 2.0, 3.0))
        self.provider.schedule_timer("ping", self.provider.current_time() + 2.0)

    def handle_timer(self, timer: str) -> None:
        self.log.append(f"timer:{timer}")
        self.provider.send_communication_command(BroadcastMessageCommand("beacon"))

    def handle_packet(self, message: str) -> None:
        self.log.append(f"packet:{message}")
        self.provider.send_communication_command(SendMessageCommand("ack", 2))

    def handle_telemetry(self, telemetry: Telemetry) -> None:
        self.log.append(f"telemetry:{telemetry.current_position}")

    def finish(self) -> None:
        self.log.append("finished")


def _legacy_instance(protocol: LegacyProtocolAdapter) -> OldStyleProtocol:
    inner = protocol.legacy_protocol
    assert isinstance(inner, OldStyleProtocol)
    return inner


def test_is_legacy_detects_old_style_classes() -> None:
    assert is_legacy(OldStyleProtocol)
    assert not is_legacy(LegacyProtocolAdapter)


def test_legacy_is_idempotent_per_class() -> None:
    assert legacy(OldStyleProtocol) is legacy(OldStyleProtocol)


def test_initialize_runs_and_commands_are_translated() -> None:
    host = FakeHost()
    adapter: LegacyProtocolAdapter = install(host, OldStyleProtocol)

    assert SetSpeed(5.0) in host.commands
    assert GotoCoords(1.0, 2.0, 3.0) in host.commands
    assert TrackVariable("state", "up") in host.commands
    assert host.tracked == [("state", "up")]
    assert adapter.tracked_variables["state"] == "up"


def test_absolute_timestamps_become_relative_delays() -> None:
    host = FakeHost(start_time=100.0)
    install(host, OldStyleProtocol)
    scheduled = [c for c in host.commands if isinstance(c, ScheduleTimer)]
    # legacy scheduled at current_time() + 2.0 == 102.0 absolute
    assert scheduled == [ScheduleTimer("ping", 2.0)]


def test_timer_reaches_the_legacy_handler() -> None:
    host = FakeHost()
    adapter: LegacyProtocolAdapter = install(host, OldStyleProtocol)
    host.advance(3.0)
    assert _legacy_instance(adapter).log == ["timer:ping"]
    assert Broadcast("beacon") in host.commands


def test_packet_reaches_the_legacy_handler_with_source_dropped() -> None:
    host = FakeHost()
    adapter: LegacyProtocolAdapter = install(host, OldStyleProtocol)
    host.deliver_packet("hello", source=7)
    # The legacy signature has nowhere to put source -- this is the documented fidelity.
    assert _legacy_instance(adapter).log == ["packet:hello"]
    assert SendMessage("ack", 2) in host.commands


def test_telemetry_is_rewrapped_into_the_legacy_message() -> None:
    host = FakeHost()
    adapter: LegacyProtocolAdapter = install(host, OldStyleProtocol)
    host.deliver_telemetry((4.0, 5.0, 6.0))
    assert _legacy_instance(adapter).log == ["telemetry:(4.0, 5.0, 6.0)"]


def test_stop_calls_finish() -> None:
    host = FakeHost()
    adapter: LegacyProtocolAdapter = install(host, OldStyleProtocol)
    host.binding.stop()
    assert _legacy_instance(adapter).log[-1] == "finished"


def test_cancel_timer_translates() -> None:
    class Canceller(IProtocol):
        def initialize(self) -> None:
            self.provider.schedule_timer("a", self.provider.current_time() + 1.0)
            self.provider.schedule_timer("a", self.provider.current_time() + 2.0)
            self.provider.cancel_timer("a")

        def handle_timer(self, timer: str) -> None:
            raise AssertionError("cancelled timer fired")

        def handle_packet(self, message: str) -> None: ...
        def handle_telemetry(self, telemetry: Telemetry) -> None: ...
        def finish(self) -> None: ...

    host = FakeHost()
    install(host, Canceller)
    assert CancelTimer("a") in host.commands
    host.advance(5.0)  # must not raise -- cancel-all semantics


def test_geo_coords_translate() -> None:
    class Geo(IProtocol):
        def initialize(self) -> None:
            self.provider.send_mobility_command(
                GotoGeoCoordsMobilityCommand(-15.84, -47.92, 20.0)
            )

        def handle_timer(self, timer: str) -> None: ...
        def handle_packet(self, message: str) -> None: ...
        def handle_telemetry(self, telemetry: Telemetry) -> None: ...
        def finish(self) -> None: ...

    host = FakeHost()
    install(host, Geo)
    from gradys_core import GotoGeoCoords

    assert GotoGeoCoords(-15.84, -47.92, 20.0) in host.commands


def test_send_without_destination_is_a_loud_error() -> None:
    """The legacy provider warned and silently dropped the message."""

    class NoDest(IProtocol):
        def initialize(self) -> None:
            self.provider.send_communication_command(SendMessageCommand("x", None))

        def handle_timer(self, timer: str) -> None: ...
        def handle_packet(self, message: str) -> None: ...
        def handle_telemetry(self, telemetry: Telemetry) -> None: ...
        def finish(self) -> None: ...

    with pytest.raises(ValueError, match="destination"):
        install(FakeHost(), NoDest)


def test_broadcast_command_equality_is_fixed() -> None:
    """The originals bypassed the dataclass __init__, leaving fields unset."""
    assert BroadcastMessageCommand("x") == BroadcastMessageCommand("x")
    assert SendMessageCommand("x", 1) == SendMessageCommand("x", 1)
    assert BroadcastMessageCommand("x").destination is None


def test_adapter_declares_the_full_legacy_command_set() -> None:
    declared = declared_commands(legacy(OldStyleProtocol))
    assert GotoCoords in declared
    assert ScheduleTimer in declared
    assert TrackVariable in declared


def test_capability_check_applies_to_legacy_protocols_too() -> None:
    class NoTimersHost(FakeHost):
        def register_commands(self, registry):  # type: ignore[no-untyped-def]
            registry.add(GotoCoords, self._record)

    with pytest.raises(UnsupportedCommandError):
        NoTimersHost().bind(legacy(OldStyleProtocol))
