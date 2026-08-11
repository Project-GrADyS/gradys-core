"""Event dispatch: the ordered handler chain behind :func:`gradys_core.subscribe`.

This replaces the legacy ``plugin/dispatcher.py``, which monkey-patched protocol
instance methods and tracked them in a module-global dict keyed by protocol instance.
Here the chain lives on the protocol object, nothing is patched, and ordering is
explicit rather than emergent from list-insertion order.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, List, Optional

from gradys_core.events import Event, StartEvent, StopEvent


class Disposition(Enum):
    """What a handler wants to happen after it returns.

    Successor to the legacy ``DispatchReturn``. Returning ``None`` means
    :attr:`CONTINUE`, so a handler with nothing to say can just fall off the end.
    """

    CONTINUE = "continue"
    """Pass the event to the next handler in the chain."""

    STOP = "stop"
    """Consume the event; no later handler sees it.

    Ignored for :class:`~gradys_core.events.StartEvent` and
    :class:`~gradys_core.events.StopEvent`, whose chains always run to completion.
    """


HandlerResult = Optional[Disposition]
Handler = Callable[[Any], HandlerResult]

PRIORITY_OBSERVER = -300
"""Runs before everything. For statistics and tracing.

Handlers in this band **must** return ``CONTINUE``. The legacy statistics plugin
registered as an ordinary plugin, so any ``INTERRUPT`` upstream silently blinded it.
"""

PRIORITY_PLUGIN = 0
"""Default for plugins. Runs before the protocol's own handlers."""

PRIORITY_PROTOCOL = 100
"""Default for a protocol's own handlers. Runs last."""


class _Entry:
    __slots__ = ("event", "handler", "priority", "seq", "alive")

    def __init__(self, event: type, handler: Handler, priority: int, seq: int) -> None:
        self.event = event
        self.handler = handler
        self.priority = priority
        self.seq = seq
        self.alive = True


class Subscription:
    """Handle for one registration. Cancelling is idempotent.

    The legacy dispatcher required callers to hold the exact handler function object
    and raised ``ValueError`` on a second unregister; this is the token instead.
    """

    __slots__ = ("_entry",)

    def __init__(self, entry: _Entry) -> None:
        self._entry = entry

    def cancel(self) -> None:
        """Stop delivering to this handler. Safe to call more than once."""
        self._entry.alive = False

    @property
    def active(self) -> bool:
        """False once :meth:`cancel` has been called."""
        return self._entry.alive

    def __enter__(self) -> "Subscription":
        return self

    def __exit__(self, *exc: object) -> None:
        self.cancel()


class EventBus:
    """Ordered handler chains, one logical chain per event type.

    Ordering is ``(priority, seq)`` ascending: lower priority first, ties broken by
    registration order (FIFO). The legacy dispatcher inserted at index 0, making it LIFO
    by accident; no in-tree plugin depended on that, since each one filters by tag or
    prefix and lets everything else through.
    """

    __slots__ = ("_entries", "_seq")

    def __init__(self) -> None:
        self._entries: List[_Entry] = []
        self._seq = 0

    def add(self, event: type, handler: Handler, priority: int) -> Subscription:
        entry = _Entry(event, handler, priority, self._seq)
        self._seq += 1
        self._entries.append(entry)
        self._entries.sort(key=lambda e: (e.priority, e.seq))
        return Subscription(entry)

    def dispatch(self, event: Event) -> None:
        """Deliver ``event`` to every live matching handler, in order.

        Matching walks the event's MRO, so subscribing to a base class receives its
        subclasses. Iteration is over a snapshot, so a handler may subscribe or cancel
        while the chain is running — the random-mobility plugin does exactly that, and
        plugins are constructed from inside a ``StartEvent`` handler.
        """
        mro = type(event).__mro__
        interruptible = not isinstance(event, (StartEvent, StopEvent))
        for entry in tuple(self._entries):
            if not entry.alive or entry.event not in mro:
                continue
            if entry.handler(event) is Disposition.STOP and interruptible:
                break

    def prune(self) -> None:
        """Drop cancelled entries. Purely housekeeping; dispatch already skips them."""
        self._entries = [e for e in self._entries if e.alive]
