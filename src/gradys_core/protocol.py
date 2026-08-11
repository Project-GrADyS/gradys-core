"""The protocol-author surface: :class:`Protocol`, :class:`Provider`, :func:`subscribe`.

A protocol is a pure reactor. It does exactly two things, both **through its provider**:

* **sends commands** — requests for the environment to act
* **subscribes to events** — notifications the environment delivers

It never implements a command and never publishes an event. The environment constructs a
:class:`Provider` — which owns the event bus and the whole runtime surface — and
``bind()`` injects it into the protocol, then calls :meth:`Protocol.on_bind`::

    SweepEvents   = TelemetryEvent | TimerEvent | StartEvent
    SweepCommands = GotoCoords | Broadcast | ScheduleTimer

    class SweepProtocol(Protocol[SweepEvents, SweepCommands]):
        def on_bind(self) -> None:
            subscribe(self.provider, TelemetryEvent, self._on_telemetry, PRIORITY_PROTOCOL)

        def _on_telemetry(self, e: TelemetryEvent) -> None:
            self.provider.send(GotoCoords(e.position[0], e.position[1], 30.0))

Note there is **no** ``super().__init__()`` anywhere: the base class is stateless, so a
protocol's own ``__init__`` (if any) is a plain initializer. Subscribing to an event
outside the declared set, or sending a command outside it, is a **type error** — not a
runtime surprise.
"""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Collection,
    Generic,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

from gradys_core.bus import (
    PRIORITY_PLUGIN,
    EventBus,
    HandlerResult,
    Subscription,
)
from gradys_core.commands import Command
from gradys_core.events import Event

EventT = TypeVar("EventT", bound=Event, contravariant=True)
CmdT = TypeVar("CmdT", bound=Command, contravariant=True)
_E = TypeVar("_E", bound=Event)

SupportsCheck = Union[Callable[[type], bool], Collection[type]]
"""How an environment answers "can you service this command type?".

Either a predicate over command types (``CommandRegistry.supports`` has this shape), or
a collection of command types — in which case core does the MRO-aware membership check,
so a collection containing a base class covers every subclass.
"""


class UnsupportedCommandError(Exception):
    """A protocol used a command the environment cannot service.

    Raised by ``bind()`` before the protocol is even constructed (the declared command
    set is checked against the provider), and by :meth:`Provider.send` as a backstop for
    untyped callers.
    """


class UndeclaredEventError(Exception):
    """A subscription named an event outside the protocol's declared event set.

    The static checkers catch this at edit time (mypy reports it as
    ``Cannot infer value of type parameter "_E"``); this runtime error is the backstop
    for untyped callers, raised the moment :func:`subscribe` runs on a bound provider.
    """


class NotInstalledError(RuntimeError):
    """A protocol touched ``self.provider`` before ``bind()`` injected it."""


def supports_command(supports: SupportsCheck, command: type) -> bool:
    """Evaluate a :data:`SupportsCheck` against one command type.

    A collection answer is MRO-aware: it supports ``command`` if it contains the class
    or any of its bases.
    """
    if callable(supports):
        return supports(command)
    return any(base in supports for base in command.__mro__)


class Provider(Generic[EventT, CmdT]):
    """The protocol's entire window onto its execution environment.

    Constructed by the environment from plain callables and injected by ``bind()`` —
    the environment decides what the callables do (execute synchronously, enqueue onto
    an event loop, ...); core owns the semantics. The provider also **owns the event
    bus**, which is why it exists before the protocol does and why each protocol needs
    its own provider instance.

    Type parameters mirror the bound protocol's declared sets, so a provider annotated
    ``Provider[TelemetryEvent, GotoCoords]`` is a *statically checked capability
    requirement* — any provider whose sets are supersets is accepted. Plugins use
    exactly this to declare what they need.
    """

    __slots__ = ("bus", "bound_to", "declared_events", "_node_id", "_now", "_send", "_supports")

    bus: EventBus
    """Library-internal. The handler chains behind :func:`subscribe`.

    Public only because :func:`subscribe` and ``Binding`` live in other modules and have
    to reach it; treat it as private."""

    bound_to: Optional[str]
    """Library-internal. Name of the protocol class this provider is bound to.

    Set once by ``bind()``; a provider owns one bus and therefore binds one protocol."""

    declared_events: Optional[Tuple[type, ...]]
    """Library-internal. The bound protocol's declared event set, set by ``bind()``.

    Enables the runtime membership backstop in :func:`subscribe`."""

    def __init__(
        self,
        node_id: int,
        now: Callable[[], float],
        send: Callable[[Command], None],
        supports: SupportsCheck,
    ) -> None:
        """Build a provider from the environment's parts.

        Args:
            node_id: this node's unique identifier.
            now: returns the node's single time reference (see :meth:`now`).
            send: executes a command. May run it synchronously (a simulator) or
                enqueue it (an async runtime); commands are frozen, so they are safe
                to hand across such a boundary. Only ever receives command types that
                ``supports`` admitted.
            supports: the environment's capability answer, used by the ``bind()``-time
                gate and by :meth:`send`'s backstop.
        """
        self.bus = EventBus()
        self.bound_to = None
        self.declared_events = None
        self._node_id = node_id
        self._now = now
        self._send = send
        self._supports = supports

    def node_id(self) -> int:
        """This node's unique identifier."""
        return self._node_id

    def now(self) -> float:
        """The node's **single time reference**: monotonic seconds, unspecified epoch.

        Only *differences* are meaningful, and only on this node — the value is
        **never** comparable across nodes (the simulator counts from zero, the embedded
        runtime returns ``loop.time()``). There is deliberately no cross-node clock in
        this contract; prefer ``ScheduleTimer(tag, delay)`` over arithmetic on this.
        """
        return self._now()

    def supports(self, command: type) -> bool:
        """True if the environment can service ``command`` (or a registered base of it)."""
        return supports_command(self._supports, command)

    def send(self, command: CmdT) -> None:
        """Ask the environment to perform ``command``.

        Fire-and-forget: there is no return value and no delivery guarantee. Results,
        if any, arrive later as events. The command must be in the protocol's declared
        command set — enforced statically, and re-checked here so untyped callers get
        the same :class:`UnsupportedCommandError` no matter what the environment's
        ``send`` callable does.
        """
        if not self.supports(type(command)):
            raise UnsupportedCommandError(
                f"{type(command).__name__} is not supported by this environment "
                f"(provider bound to {self.bound_to or '(nothing yet)'})."
            )
        self._send(command)


class Protocol(Generic[EventT, CmdT]):
    """Base class for every protocol. Deliberately stateless.

    Type parameters:
        EventT: union of the event types this protocol may subscribe to.
        CmdT: union of the command types this protocol may send. This doubles as the
            protocol's capability contract — binding it to an environment that cannot
            service one of these fails immediately, by name, before construction.

    Both parameters are **contravariant**, which is what makes set membership
    expressible: ``Provider[A | B | C]`` is a subtype of ``Provider[A]`` exactly
    because ``A`` is a subtype of ``A | B | C``. That is also why a plugin can declare
    only what it needs (``Provider[TelemetryEvent, GotoCoords]``) and accept the
    provider of any protocol whose declared sets are supersets.

    The base holds **no instance state** — ``provider`` is injected by ``bind()`` —
    so subclasses never call ``super().__init__()``. Subscriptions belong in
    :meth:`on_bind` (or later, from handlers), never in ``__init__``, because the
    provider does not exist there yet.
    """

    provider: Provider[EventT, CmdT]
    """The environment's runtime surface, injected by ``bind()``."""

    def on_bind(self) -> None:
        """Hook called by ``bind()`` once ``self.provider`` is injected.

        Override to register handlers::

            def on_bind(self) -> None:
                subscribe(self.provider, TelemetryEvent, self._on_telemetry,
                          PRIORITY_PROTOCOL)

        A protocol subclassing another protocol extends the parent's subscriptions by
        calling ``super().on_bind()`` — opt-in composition, not an obligation.
        """

    if not TYPE_CHECKING:
        # Runtime-only diagnostic, hidden from type checkers so a __getattr__ does not
        # silence attribute typos on every protocol subclass.
        def __getattr__(self, name: str) -> Any:
            if name == "provider":
                raise NotInstalledError(
                    f"{type(self).__name__}.provider is not set yet: it is injected "
                    f"by bind(). Subscribe and send from on_bind() or from event "
                    f"handlers, not from __init__."
                )
            raise AttributeError(
                f"{type(self).__name__!r} object has no attribute {name!r}"
            )


ProtocolBase = Protocol
"""Alias for :class:`Protocol`, for modules that also need ``typing.Protocol``."""


def subscribe(
    provider: Provider[_E, Any],
    event: type[_E],
    handler: Callable[[_E], HandlerResult],
    priority: int = PRIORITY_PLUGIN,
) -> Subscription:
    """Register ``handler`` to receive ``event`` from ``provider``.

    This is the only registration mechanism. Protocols and plugins use the identical
    call — a protocol passes ``self.provider``, a plugin passes the provider it was
    given.

    Args:
        provider: the provider to register on.
        event: the event type. Must be a member of the declared event set (or a
            subtype of one), **checked statically**; subscribing to a base class also
            receives its subclasses.
        handler: called with the event. Return ``Disposition.STOP`` to consume it,
            ``CONTINUE`` or ``None`` to pass it on.
        priority: lower runs first. See ``PRIORITY_OBSERVER`` / ``PRIORITY_PLUGIN`` /
            ``PRIORITY_PROTOCOL``. Ties break by registration order.

    Returns:
        A :class:`Subscription`; call ``cancel()`` to stop delivery.

    Raises:
        UndeclaredEventError: runtime backstop of the static membership check, for
            untyped callers on a bound provider.

    Note:
        This is a module-level function rather than a ``Provider`` method for a
        load-bearing, checker-verified reason: a method cannot express "``_E`` is both
        the handler's event type and a member of the declared union" — the self-type is
        bound before inference, freezing ``_E`` to the whole union. As a function, all
        three arguments are solved jointly. If mypy reports ``Cannot infer value of
        type parameter "_E"``, it means the event is not in the declared event set.
    """
    declared = provider.declared_events
    if declared is not None and not any(issubclass(event, d) for d in declared):
        raise UndeclaredEventError(
            f"{event.__name__} is not in the declared event set of "
            f"{provider.bound_to}: {', '.join(d.__name__ for d in declared)}. "
            f"Declare it in the protocol's Protocol[Events, Commands] parameterization."
        )
    return provider.bus.add(event, handler, priority)
