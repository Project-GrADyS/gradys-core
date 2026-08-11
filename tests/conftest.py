"""Fixtures shared by the runtime test suite. See tests/README.md for the test map."""

from __future__ import annotations

from typing import Any, Callable

import pytest

from gradys_core.testing import FakeHost


@pytest.fixture
def host() -> FakeHost:
    """A fresh fully-capable fake environment (manual clock at 0, node id 1)."""
    return FakeHost()


@pytest.fixture
def bound(host: FakeHost) -> Callable[[type], Any]:
    """bind + start a protocol class on ``host``; returns the protocol instance."""
    return host.install
