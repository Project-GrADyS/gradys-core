"""The environment-side contract: build a :class:`Provider`, :func:`bind`, drive the :class:`Binding`.

gradys-core deliberately does **not** prescribe an execution environment's
infrastructure. The simulator is centralized (one process, many nodes, shared memory);
the embedded runtime is decentralized (one node per process, async I/O); a fixed host
structure would fit one of them badly. Instead, the environment expresses itself as
plain callables wrapped in a :class:`~gradys_core.protocol.Provider`, and core owns
only the two invariants worth never implementing twice:

* **the capability gate** — a protocol's declared command set is checked against what
  the provider supports *before* the protocol is constructed, and

* **lifecycle ordering** — ``StartEvent`` is delivered first and once, ``StopEvent``
  last and once, and nothing is delivered outside that window.

The environment constructs one provider per protocol (the provider owns that
protocol's event bus), calls :func:`bind`, and uses the returned :class:`Binding` as
the **only** path by which events reach the protocol. Everything else — threading,
memory layout, transports, scheduling, whether a registry exists at all — is the
environment's business.

:class:`CommandRegistry` below is an optional convenience with the right shapes for
the provider's ``send`` and ``supports`` callables; environments are free to ignore it.
"""

from __future__ import annotations

from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Tuple,
    TypeVar,
    get_args,
    get_origin,
)

from gradys_core.commands import Command
from gradys_core.events import Event, StartEvent, StopEvent
from gradys_core.protocol import (
    Protocol,
    Provider,
    SupportsCheck,
    UnsupportedCommandError,
    supports_command,
)

__all__ = [
    "Binding",
    "CommandRegistry",
    "SupportsCheck",
    "UnsupportedCommandError",
    "bind",
    "check_capabilities",
    "declared_commands",
    "declared_events",
]

_C = TypeVar("_C", bound=Command)
_P = TypeVar("_P", bound=Protocol[Any, Any])


class CommandRegistry:
    """Optional helper: maps command types to the code that performs them.

    Not part of the contract — a :class:`~gradys_core.protocol.Provider` only sees
    callables, and an environment may dispatch commands any way it likes. This exists
    because ``dispatch`` and ``supports`` have exactly the shapes
    ``Provider(send=..., supports=...)`` expects, and because lookup walks the
    command's MRO, so one handler registered against
    :class:`~gradys_core.commands.MobilityCommand` services every subclass.
    """

    __slots__ = ("_handlers",)

    def __init__(self) -> None:
        self._handlers: Dict[type, Callable[[Any], None]] = {}

    def add(self, command: type[_C], handler: Callable[[_C], None]) -> None:
        """Register ``handler`` as the implementation of ``command``."""
        self._handlers[command] = handler

    def supports(self, command: type) -> bool:
        """True if this registry can service ``command`` or one of its bases."""
        return any(base in self._handlers for base in command.__mro__)

    def dispatch(self, command: Command) -> None:
        for base in type(command).__mro__:
            handler = self._handlers.get(base)
            if handler is not None:
                handler(command)
                return
        raise UnsupportedCommandError(
            f"No handler registered for {type(command).__name__}. "
            f"Registered: {', '.join(self.names()) or '(none)'}"
        )

    def names(self) -> List[str]:
        return sorted(c.__name__ for c in self._handlers)


def _declared(cls: type, index: int) -> Tuple[type, ...]:
    """Recover one declared set from a ``Protocol[Events, Commands]`` parameterization.

    Walks the MRO so a subclass of an already-parameterized protocol inherits its sets.
    Handles both a union and a single bare type. Raises rather than returning ``()``
    on a shape it cannot parse — a silently-empty declared set would make the
    capability check vacuous.
    """
    for klass in cls.__mro__:
        for base in getattr(klass, "__orig_bases__", ()):
            if get_origin(base) is Protocol:
                args = get_args(base)
                if len(args) != 2:
                    continue
                member = args[index]
                inner = get_args(member)
                members: Tuple[Any, ...] = inner if inner else (member,)
                bad = [m for m in members if m is Any or not isinstance(m, type)]
                if bad:
                    raise TypeError(
                        f"{cls.__name__} parameterizes Protocol with "
                        f"{', '.join(repr(m) for m in bad)}, which cannot be checked "
                        f"at install time. Declared event and command sets must be "
                        f"concrete classes or unions of them — no TypeVars, no Any."
                    )
                return members
    if issubclass(cls, Protocol):
        raise TypeError(
            f"{cls.__name__} subclasses Protocol but declares no event/command sets. "
            f"Parameterize it, e.g. "
            f"`class {cls.__name__}(Protocol[MyEvents, MyCommands])` — the command "
            f"set is the capability contract checked at install time."
        )
    return ()


def declared_events(cls: type) -> Tuple[type, ...]:
    """The event types ``cls`` declared, flattened out of its union."""
    return _declared(cls, 0)


def declared_commands(cls: type) -> Tuple[type, ...]:
    """The command types ``cls`` declared — its capability contract."""
    return _declared(cls, 1)


def _supported_names(supports: SupportsCheck) -> str:
    if callable(supports):
        return "(opaque predicate)"
    return ", ".join(sorted(c.__name__ for c in supports)) or "(none)"


def check_capabilities(protocol_cls: type, supports: SupportsCheck) -> None:
    """Verify the environment can service every command ``protocol_cls`` declared.

    Args:
        protocol_cls: a ``Protocol[Events, Commands]`` subclass.
        supports: the environment's capability answer; see
            :data:`~gradys_core.protocol.SupportsCheck`.

    Raises:
        UnsupportedCommandError: naming the missing commands.
        TypeError: if the declared sets cannot be recovered from ``protocol_cls``.
    """
    declared = declared_commands(protocol_cls)
    missing = [c for c in declared if not supports_command(supports, c)]
    if missing:
        raise UnsupportedCommandError(
            f"{protocol_cls.__name__} declares command(s) "
            f"{', '.join(m.__name__ for m in missing)} but the environment "
            f"supports no handler for them.\n"
            f"  declared : {', '.join(c.__name__ for c in declared) or '(none)'}\n"
            f"  supported: {_supported_names(supports)}\n"
            f"  missing  : {', '.join(m.__name__ for m in missing)}"
        )


class Binding(Generic[_P]):
    """One installed protocol, and the only path by which events reach it.

    Created by :func:`bind`. Owns the lifecycle invariants so no environment has to
    re-implement them: ``StartEvent`` first and once, ``StopEvent`` last and once,
    every delivery outside the started window silently dropped.
    """

    __slots__ = ("protocol", "provider", "_started", "_stopped")

    def __init__(self, protocol: _P, provider: Provider[Any, Any]) -> None:
        self.protocol = protocol
        self.provider = provider
        self._started = False
        self._stopped = False

    def deliver(self, event: Event) -> None:
        """Publish ``event`` to the protocol.

        Host-side only — protocols cannot emit events. Delivering before
        :meth:`start` or after :meth:`stop` is a documented no-op, which is what
        enforces "StartEvent first, StopEvent last" structurally.
        """
        if not self._started or self._stopped:
            return
        self.provider.bus.dispatch(event)

    def start(self) -> None:
        """Deliver :class:`~gradys_core.events.StartEvent`. Idempotent.

        A no-op on a binding that was already stopped: a closed binding stays closed.
        """
        if self._started or self._stopped:
            return
        self._started = True
        self.deliver(StartEvent())

    def stop(self, reason: str = "shutdown") -> None:
        """Deliver :class:`~gradys_core.events.StopEvent`, then close the binding.

        Idempotent. If the binding was never started, no ``StopEvent`` is delivered —
        a protocol must not observe a stop without its matching start.
        """
        if self._stopped:
            return
        if self._started:
            self.deliver(StopEvent(reason))
        self._stopped = True


def bind(cls: type[_P], provider: Provider[Any, Any]) -> Binding[_P]:
    """Wire a protocol class to an execution environment's provider.

    Runs the capability check **before** constructing ``cls`` — a protocol the
    environment cannot service never runs, not even its ``__init__``. Then constructs
    the protocol with a plain ``cls()`` (no ``super().__init__()`` contract; the
    ``instantiate()`` classmethod survives only in :mod:`gradys_core.legacy`), injects
    ``provider``, and calls :meth:`~gradys_core.protocol.Protocol.on_bind` so the
    protocol can register its handlers.

    Args:
        cls: the ``Protocol[Events, Commands]`` subclass to install.
        provider: the environment's :class:`~gradys_core.protocol.Provider`. One per
            protocol — the provider owns the protocol's event bus.

    Raises:
        UnsupportedCommandError: if the environment cannot service a declared command.
        TypeError: if ``cls`` is not a parameterized ``Protocol`` subclass.
        RuntimeError: if ``provider`` is already bound to another protocol.
    """
    candidate: type = cls  # widened so the runtime guard survives strict checkers
    try:
        is_protocol = issubclass(candidate, Protocol)
    except TypeError:  # not a class at all (e.g. a generic alias or an instance)
        is_protocol = False
    if not is_protocol:
        raise TypeError(f"bind() requires a Protocol subclass, got {cls!r}")
    if provider.bound_to is not None:
        raise RuntimeError(
            f"this Provider is already bound to {provider.bound_to}. A provider owns "
            f"one event bus, so each protocol needs its own Provider instance."
        )
    check_capabilities(cls, provider.supports)
    protocol = cls()
    protocol.provider = provider
    provider.bound_to = cls.__name__
    provider.declared_events = declared_events(cls)
    protocol.on_bind()
    return Binding(protocol, provider)
