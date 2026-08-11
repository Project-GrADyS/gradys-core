"""FakeHost is the reference environment: it must pass its own conformance suite.

This also proves the suite is runnable at all — every downstream environment
(gradysim, gradys-embedded) subclasses ``HostConformance`` the exact same way.
"""

from __future__ import annotations

from typing import Any, Sequence

from gradys_core import Binding, Command
from gradys_core.testing import ConformanceHarness, FakeHost, HostConformance


class _FakeHostHarness(ConformanceHarness):
    def __init__(self) -> None:
        self.host = FakeHost()

    def bind(self, protocol_cls: type) -> Binding[Any]:
        return self.host.bind(protocol_cls)

    def executed(self) -> Sequence[Command]:
        return list(self.host.commands)

    def advance(self, seconds: float) -> None:
        self.host.advance(seconds)


class TestFakeHostConformance(HostConformance):
    supports_mobility = True
    supports_timers = True

    def make_harness(self) -> ConformanceHarness:
        return _FakeHostHarness()


class TestPoorEnvironmentConformance(HostConformance):
    """The suite must also pass for an environment with fewer capabilities."""

    supports_mobility = False
    supports_timers = False

    def make_harness(self) -> ConformanceHarness:
        harness = _FakeHostHarness()

        class _CommsOnly(FakeHost):
            def register_commands(self, registry: Any) -> None:
                from gradys_core import Broadcast

                registry.add(Broadcast, self._record)

        harness.host = _CommsOnly()
        return harness
