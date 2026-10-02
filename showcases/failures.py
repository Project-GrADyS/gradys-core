"""Capability failures during binding and after binding.

Run from the repository root with ``python -m showcases.failures``.
"""

from gradys_core.capabilities.lifecycle import SimulationInitializationEvent
from gradys_core.capabilities.mobility import GotoCoords, PositionUpdate
from gradys_core.errors import ProtocolSetUpException
from gradys_core.protocol import BaseProtocol

from .checks import check
from .mock_environment import MockEnvironment


class NeedsMovement(BaseProtocol):
    def __init__(self) -> None:
        super().__init__()
        self.move = self.require_command(GotoCoords)
        self.move.send(GotoCoords(1.0, 2.0, 3.0))


class NeedsPosition(BaseProtocol):
    def __init__(self) -> None:
        super().__init__()
        self.require_event(PositionUpdate).subscribe(lambda event: None)


class LifecycleOnly(BaseProtocol):
    def __init__(self) -> None:
        super().__init__()
        self.require_event(SimulationInitializationEvent).subscribe(lambda event: None)


def main() -> None:
    print("Failures: missing capabilities")
    without_mobility = MockEnvironment(mobility=False)
    movement = NeedsMovement()
    try:
        without_mobility.bind(movement)
    except ProtocolSetUpException as error:
        check("GotoCoords" in error.message, "missing command rejects binding")
    else:
        raise AssertionError("Binding should reject GotoCoords")
    check(without_mobility.executed == [], "rejected protocol executes nothing")

    try:
        movement.move.send(GotoCoords(4.0, 5.0, 6.0))
    except RuntimeError:
        check(True, "rejected protocol is unusable")
    else:
        raise AssertionError("A failed connection should reject commands")

    try:
        MockEnvironment(mobility=False).bind(NeedsPosition())
    except ProtocolSetUpException as error:
        check("PositionUpdate" in error.message, "missing event rejects binding")
    else:
        raise AssertionError("Binding should reject PositionUpdate")

    lifecycle = LifecycleOnly()
    without_mobility.bind(lifecycle)
    try:
        lifecycle.require_event(PositionUpdate)
    except ProtocolSetUpException as error:
        check("PositionUpdate" in error.message, "missing requirement after binding is rejected")
    else:
        raise AssertionError("A later missing requirement should be rejected")


if __name__ == "__main__":
    main()
