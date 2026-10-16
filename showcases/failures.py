"""Immediate capability failures through a connected context.

Run from the repository root with ``python -m showcases.failures``.
"""

from gradys_core.capabilities.lifecycle import SimulationInitializationEvent
from gradys_core.capabilities.mobility import GotoCoords, PositionUpdate
from gradys_core.errors import ProtocolSetUpException
from gradys_core.protocol import BaseProtocol, ProtocolContext

from .checks import check
from .mock_environment import MockEnvironment


class NeedsMovement(BaseProtocol):
    """Request mobility from the supplied context."""

    def run(self, context: ProtocolContext) -> None:
        """Check movement support before any asynchronous send is attempted."""
        self.move = context.require_command(GotoCoords)


class NeedsPosition(BaseProtocol):
    """Request position observations from the supplied context."""

    def run(self, context: ProtocolContext) -> None:
        """Check event support before registering a handler."""
        context.require_event(PositionUpdate).subscribe(lambda event: None)


class LifecycleOnly(BaseProtocol):
    """Use lifecycle support without requiring mobility."""

    def run(self, context: ProtocolContext) -> None:
        """Register an initialization handler."""
        context.require_event(SimulationInitializationEvent).subscribe(lambda event: None)


def main() -> None:
    """Check immediate rejection during run and subsequent context use."""
    environment = MockEnvironment(mobility=False)
    for protocol, capability in [(NeedsMovement(), "GotoCoords"), (NeedsPosition(), "PositionUpdate")]:
        try:
            environment.bind(protocol)
        except ProtocolSetUpException as error:
            check(capability in error.message, "missing capability raises immediately")
        else:
            raise AssertionError("An unsupported requirement should fail")
    check(environment.executed == [], "rejected movement was never sent")

    context = environment.bind(LifecycleOnly())
    try:
        context.require_event(PositionUpdate)
    except ProtocolSetUpException as error:
        check("PositionUpdate" in error.message, "later requirements are also validated")
    else:
        raise AssertionError("A later missing requirement should fail")


if __name__ == "__main__":
    main()
