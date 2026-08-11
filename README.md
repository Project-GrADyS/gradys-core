# gradys-core

The protocol interface shared by [GrADyS-SIM NextGen](https://github.com/Project-GrADyS/gradys-sim-nextgen)
and [gradys-embedded](../gradys-embedded). One definition, imported by both, so the
contract cannot drift.

## The model

A protocol is a **pure reactor**. It does exactly two things:

- **sends Commands** — requests for the environment to act
- **subscribes to Events** — notifications the environment delivers

It never implements a command and never publishes an event — and it does both **through
its `Provider`**, the single object the environment injects that carries the node's
identity, its clock, `send`, and the event bus. Each execution environment (the
simulator, the embedded runner, a test harness) builds a provider from its own
machinery and drives the delivery of every event it produces.

That is what makes the interface extensible. Timers, mobility, communication, sensors
and actuators are all just command/event pairs on equal footing — none is privileged by
the core. A new capability is a new `Command` subclass, whatever `Event` subclasses
report its results, and an environment that executes it. The core never changes.

## A protocol

```python
from gradys_core import (
    Protocol, subscribe, PRIORITY_PROTOCOL, Disposition,
    StartEvent, TelemetryEvent, PacketEvent, TimerEvent,
    GotoCoords, Broadcast, ScheduleTimer,
)

SweepEvents   = StartEvent | TelemetryEvent | PacketEvent | TimerEvent
SweepCommands = GotoCoords | Broadcast | ScheduleTimer


class SweepProtocol(Protocol[SweepEvents, SweepCommands]):
    def on_bind(self) -> None:
        # called by bind() once self.provider is injected -- subscribe HERE, not in __init__
        subscribe(self.provider, StartEvent, self._on_start, PRIORITY_PROTOCOL)
        subscribe(self.provider, TelemetryEvent, self._on_telemetry, PRIORITY_PROTOCOL)
        subscribe(self.provider, PacketEvent, self._on_packet, PRIORITY_PROTOCOL)

    def _on_start(self, e: StartEvent) -> None:
        self.provider.send(GotoCoords(0.0, 0.0, 30.0))
        self.provider.send(ScheduleTimer("beacon", 5.0))

    def _on_telemetry(self, e: TelemetryEvent) -> None:
        x, y, z = e.position          # typed

    def _on_packet(self, e: PacketEvent) -> Disposition:
        print(f"from {e.source}: {e.payload}")   # source is present, and typed
        return Disposition.CONTINUE
```

The base class is **stateless**: a protocol that wants state of its own writes a plain
`__init__` — there is no `super().__init__()` to remember. A protocol subclassing
another protocol extends the parent's subscriptions with `super().on_bind()`, opt-in.

The two unions are the protocol's declared sets, and they are enforced by the type
checker:

```python
subscribe(self.provider, BatteryEvent, self._on_battery)  # error: not in SweepEvents
self.provider.send(SetSpeed(5.0))                         # error: not in SweepCommands
```

You may subscribe to a declared type **or any subtype of it**, never to a supertype —
declaring `TelemetryEvent` does not entitle you to every event. A genuine catch-all
observer declares `Event` itself.

## Capabilities come free

The declared command union **is** the capability contract. There is no separate
`requires`, so the two cannot drift. `bind()` checks it before the protocol is even
constructed:

```
UnsupportedCommandError: SweepProtocol declares command(s) SetGimbal but the
  environment supports no handler for them.
    declared : GotoCoords, Broadcast, ScheduleTimer, SetGimbal
    supported: GotoCoords, GotoGeoCoords, SendMessage, Broadcast, ScheduleTimer
    missing  : SetGimbal
```

Plugins get the same guarantee at the call site. A plugin declares only what it needs
on its `Provider` parameter, and contravariance accepts the provider of any protocol
whose declared sets are supersets — while the plugin's own body is checked against the
contract it declared:

```python
class MissionPlugin:
    def __init__(self, provider: Provider[TelemetryEvent, GotoCoords | SetSpeed]) -> None:
        self._sub = subscribe(provider, TelemetryEvent, self._on_telemetry)

MissionPlugin(sweep.provider)   # ok: SweepProtocol's sets are supersets
MissionPlugin(poor.provider)    # type error: missing TelemetryEvent/GotoCoords
```

## Handler ordering

Handlers run in `(priority, registration order)` — lower priority first, ties FIFO.

| band | value | for |
|---|---|---|
| `PRIORITY_OBSERVER` | -300 | statistics, tracing. Must return `CONTINUE`. |
| `PRIORITY_PLUGIN` | 0 | plugins (default) |
| `PRIORITY_PROTOCOL` | 100 | the protocol's own handlers |

Return `Disposition.STOP` to consume an event; `CONTINUE` or `None` passes it on.
`StartEvent` and `StopEvent` ignore `STOP`, so one plugin cannot skip another's setup or
teardown.

## Timers

Timers are ordinary commands, not a special API:

```python
self.provider.send(ScheduleTimer("beacon", 5.0))  # delay is RELATIVE
self.provider.send(CancelTimer("beacon"))         # cancels EVERY pending timer with that tag
```

`delay` is relative on purpose: the simulator counts from zero and the embedded runner
uses `loop.time()`, and a relative delay keeps that disagreement out of protocol code.
Timers carry no handle — a command is fire-and-forget and cannot return one — so a tag is
the only identity a timer has. Encode uniqueness in the tag if you need it.

## The environment contract

gradys-core deliberately does **not** prescribe an execution environment's
infrastructure. The simulator is centralized (one process, many nodes); the embedded
runtime is decentralized (one node per process, async I/O); a fixed host structure would
fit one of them badly. The contract is a narrow seam of plain callables, and core owns
only the two invariants worth never implementing twice: the **capability gate** and
**lifecycle ordering**.

```python
from gradys_core import bind, CommandRegistry, PacketEvent, Provider

registry = CommandRegistry()               # optional helper; any callables work
registry.add(MobilityCommand, my_mobility) # one handler services the whole family
registry.add(ScheduleTimer, my_scheduler)

provider = Provider(
    node_id=3,                      # this node's identity
    now=engine.time,                # the node's single time reference
    send=registry.dispatch,         # executes commands; may run sync or enqueue
    supports=registry.supports,     # or a plain collection of command types
)

binding = bind(SweepProtocol, provider)      # capability check HERE, before __init__

binding.start()                              # delivers StartEvent, exactly once
binding.deliver(PacketEvent("hi", source=2)) # the only publish path
binding.stop()                               # delivers StopEvent, then closes
```

The `Binding` guarantees `StartEvent` is first, `StopEvent` is last, and anything
delivered outside that window is dropped. Everything else — threading, memory layout,
transports, scheduling, whether a registry exists at all — is the environment's
business. An asynchronous environment passes a `send` that enqueues
(`lambda c: loop.create_task(execute(c))`); commands are frozen, so they are safe to
hand across that boundary.

The `Provider` **owns the protocol's event bus** — which is why it exists before the
protocol does, why each protocol needs its own provider instance, and why the base
`Protocol` class can be stateless. Its query half (`node_id()`, `now()`) is the one
surface that is neither command nor event, deliberately: a command is fire-and-forget
and cannot return a value, so modelling reads as commands would need a request/response
event pair for every query. `now()` is the node's **single time reference**: node-local
monotonic seconds, differences only, never comparable across nodes.

Behavioral obligations the seam cannot enforce — executing accepted commands faithfully,
delivering events with truthful content — are covered by the **conformance suite**.
Every environment subclasses it once in its own test tree:

```python
from gradys_core.testing import ConformanceHarness, HostConformance

class TestMyEnvironmentConformance(HostConformance):
    supports_timers = True

    def make_harness(self) -> ConformanceHarness:
        return MyEnvironmentHarness()   # wraps your real wiring; see conformance.py
```

## Running old protocols

An unmodified `IProtocol` subclass runs on any new environment:

```python
from gradys_core.legacy import legacy
binding = bind(legacy(MyOldProtocol), provider)
```

The adapter translates the four legacy provider calls into commands, converts absolute
timer timestamps into relative delays, and turns `tracked_variables` writes into
`TrackVariable` commands. `PacketEvent.source` is dropped, because the legacy
`handle_packet(message: str)` has nowhere to put it — that is the fidelity the adapter
promises, and the reason to migrate.

Only this direction is supported. New-style protocols do not run on the old simulator,
old plugins are not guaranteed to work, and the OMNeT++ consequence model is not preserved.

## Testing

`gradys_core.testing.FakeHost` is public API — a deterministic fake environment with a
manual clock, an ordered timer queue and captured commands. It is also the reference
implementation of the environment contract and passes the conformance suite:

```python
from gradys_core.testing import FakeHost, install

host = FakeHost()
protocol = install(host, SweepProtocol)      # wraps legacy classes automatically
host.deliver_packet("ping", source=2)
host.advance(5.0)                            # fires due timers, in order
assert ScheduleTimer("beacon", 5.0) in host.commands
```

## Development

```bash
pip install -e ".[dev]"
./check.sh          # pytest + mypy + pyright
```

The static suites under `tests/static/` are the primary contract, not an afterthought:

- `positive.py` must produce **zero** diagnostics — a finding there is a false positive,
  meaning the encoding rejects legitimate code.
- `negative.py` annotates every expected failure with `# type: ignore[...]` and runs under
  `--warn-unused-ignores`. The pass condition is again zero output: an error that stops
  firing surfaces as an unused ignore, so the guarantee cannot silently become vacuous.

**Run both checkers.** They disagreed on three of the five encodings tried while designing
this; a single one would have shipped a broken guarantee. Both versions are pinned.

### Why `subscribe` is a function, not a method (or a decorator)

A complete `subscribe` needs a method-scoped type variable (the event, so handlers stay
narrowly typed) *bounded by* a class-scoped one (the declared union, for membership) —
a relation Python's type system cannot declare. Every alternative was tried against
both pinned checkers and loses one half:

- **Method with a self-annotation** (`self: Provider[_E, Any]`): checkers bind the
  self-type first and freeze `_E` to the *entire* declared union, so the handler never
  narrows and even correct calls fail.
- **Method typed `event: type[EventT]`**: membership works, but every handler must
  accept the whole declared union and `isinstance`-narrow inside.
- **A decorator**: receives the *method*, where the class sits in a callable parameter
  position — contravariance flips the required subtyping to "supertype must be a
  subtype of the concrete class", which never holds. Membership is unobtainable at
  edit time for any decorator.

As a module-level function taking the provider, all three arguments are solved jointly
and both halves hold. A side benefit: protocols and plugins use the identical call.

If mypy reports `Cannot infer value of type parameter "_E"`, that **is** the membership
failure — the event is not in the declared set. Pyright's message for the same case is
precise, and the runtime backstop (`UndeclaredEventError`) names the declared set.
