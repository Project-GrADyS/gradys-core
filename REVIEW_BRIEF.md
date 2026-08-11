# `gradys-core` — review brief

Prepared for an independent reviewer. It states the task as the user set it, the design
decisions **the user made** (as distinct from ones the implementation chose), the
architecture as built, what was verified and how, and the places where the shipped code
knowingly or unknowingly departs from the approved plan.

Code under review: `/home/fleury/Documents/lac/gradys-core` (git initialised, **nothing
committed** — the whole tree is untracked). ~1360 lines of library, ~650 lines of tests.

---

## 1. The task

`gradysim` (GrADyS-SIM NextGen, upstream at `Project-GrADyS/gradys-sim-nextgen`) and
`gradys-embedded` (the local fork that runs protocols on real drones) duplicate their
protocol contract. `gradys-embedded/gradys_embedded/protocol/interface.py` is
**byte-identical** to upstream `gradysim/protocol/interface.py` — a mechanical
`gradysim.` → `gradys_embedded.` rewrite, likewise for `messages/`, `position.py` and
`plugin/`. Any change to the contract must be made twice, by hand, with nothing enforcing
agreement.

The user asked for two things at once:

1. **Extract the shared interface** into a separate repository that both projects import.
2. **Make it extensible.** The old interface is closed: a protocol reacts to exactly three
   events (telemetry, packet, timer) via fixed methods, and issues exactly three command
   families (mobility, communication, timer). The user wants users to be able to define
   **new events and commands** that add functionality to the framework, declared per
   protocol, with **static type checking** on them.
3. **Emulate old-interface protocols** on the new one.

Concrete defects in the current design that motivated this (all verified in the source):

- `handle_packet(message: str)` drops the sender. `raft_message.py` therefore injects
  `"sender_id"` into every JSON payload (`# Include sender_id for Gradysim`, ×6), and the
  `square-message-exchange` / `vertical-message-exchange` experiments hand-roll a
  `{"sender": ...}` field — while `{"message", "source"}` is **already on the wire** and is
  discarded at `communication/http.py:46` and `communication/zenoh.py:100`.
- `MobilityCommand` carries six untyped `param_1..param_6` floats whose meaning depends on
  an enum tag.
- Plugins extend behaviour by **monkey-patching protocol instance methods** through
  `plugin/dispatcher.py`, keyed off a module-global `Dict[IProtocol, ProtocolWrapper]` that
  is never cleaned up. Its `wrapped_functionality(self, *args, **kwargs)` erases all typing —
  which is why `register_initialize` still carries a vestigial `int` parameter from an
  upstream `initialize(self, stage)` that no longer exists. Wrong for years, never caught.
- `SendMessageCommand` / `BroadcastMessageCommand` assign attributes directly instead of
  calling the dataclass `__init__`, leaving `destination` unset and breaking equality.

---

## 2. Decisions the user made

These were selected by the user, not by the implementation. A reviewer should treat them as
**constraints, not proposals** — arguments against them belong in a "you may want to revisit"
section, not as findings.

| Decision | Chosen | Rejected |
|---|---|---|
| **Registration style** | `subscribe()` only | `@handles` decorator; decorator + subscribe; single `handle_event` + `match` |
| **Declared sets** | The user's own proposal: each protocol declares, *at class declaration*, the set of `Event` and `Command` subclasses it may use; using anything outside it must be a **type error** | Free use of any `Event` subclass |
| **Decorator reconciliation** | "Drop the decorator entirely" | Set-namespaced decorator (which was the recommended option); plain decorator + import-time check; both |
| **Capabilities** | "Command set is the contract" — the declared command union **is** the capability declaration | A separate `requires` attribute |
| **Protocol surface** | Protocols **strictly** send commands and subscribe to events. No `emit`, no dedicated timer API. Timers, mobility, communication, sensors, actuators are all implemented by the execution environment | An `emit` method and a first-class `Timers` API, both of which were in the first plan and were cut by the user |
| **Python floor** | 3.10 | 3.11; 3.12+; keeping 3.9 |
| **Compatibility scope** | **Only** old-protocol-on-new-runtime | New protocol on old gradysim simulator; old plugins keep working; OMNeT++ interop preserved |

Two of these are load-bearing and worth restating in the user's own words:

> "Instead of letting the user use any class that inherits from Event […] I want the user to
> declare at protocol declaration a set of classes […] If the user tries to use the decorator
> for an Event that was not registered in this set of used Events it should throw a type error"

> "Remove Timers functionality (it will be implemented through Events and Commands). Also,
> Protocols will not emit commands and/or implement commands. They will strictly send
> Commands and listen to Events, each execution environment will make sure to provide the
> necessary implementation for the Commands and the delivery of Events."

The second arrived as a rejection of the first complete plan and forced a re-verification of
the typing encoding (see §4, "Gate #1").

---

## 3. Architecture

### The model

A protocol is a **pure reactor**: it *sends commands* and *subscribes to events*, nothing
else. It never implements a command and never publishes an event. Each execution environment
supplies a `Host` that implements the commands it can service and drives the delivery of the
events it produces.

This is what buys the extensibility. A new capability is a new `Command` subclass, whatever
`Event` subclasses report its results, and a host that registers a handler. **The core never
changes.** Timers are not special: `ScheduleTimer(tag, delay)` / `CancelTimer(tag)` are
ordinary commands and `TimerEvent(tag)` an ordinary event, so a host with no timer support
simply doesn't register them and any protocol needing them fails the capability check at
install time.

### Modules (`src/gradys_core/`, zero runtime dependencies, ships `py.typed`)

| file | contents |
|---|---|
| `events.py` | `Event` base + `StartEvent`, `StopEvent`, `TelemetryEvent`, `PacketEvent`, `TimerEvent` |
| `commands.py` | `Command` base, `MobilityCommand`/`CommunicationCommand` family bases, `GotoCoords`, `GotoGeoCoords`, `SetSpeed`, `SendMessage`, `Broadcast`, `ScheduleTimer`, `CancelTimer`, `TrackVariable` |
| `protocol.py` | `Protocol[EventT, CmdT]`, module-level `subscribe`, `Provider`, `NotInstalledError` |
| `bus.py` | `EventBus`, `Subscription`, `Disposition`, priority bands |
| `host.py` | `Host`, `Runtime`, `CommandRegistry`, `declared_events`/`declared_commands`, `UnsupportedCommandError` |
| `geometry.py` | `Position`, `GeoPosition`, geo↔cartesian, distances |
| `legacy.py` | `IProtocol`/`IProvider`/`Telemetry`/old command shapes re-declared byte-compatibly + `LegacyProtocolAdapter` + `legacy()` |
| `testing.py` | `FakeHost` (public API), `install()` helper |

### Data model

Events and commands are **frozen dataclasses**. Frozen because an event is a fact that
already happened and later handlers must see what earlier ones saw, and because commands
cross gradys-embedded's fire-and-forget async boundary. Equality also makes tests read as
`assert ScheduleTimer("beacon", 5.0) in host.commands`.

Deliberate content changes from the legacy contract:

- **`PacketEvent.source` is new and mandatory.** The sender is already on the wire and
  discarded at the receive boundary; two one-line changes recover it and delete Raft's
  `sender_id` injection and the experiments' hand-rolled sender fields.
- **`TelemetryEvent.timestamp` is *sample* time, not delivery time.** gradys-embedded polls
  telemetry every 0.5 s by default, so sample age is real and mobility plugins want it.
- **`ScheduleTimer.delay` is relative, not absolute.** The two runtimes disagree on clock
  epoch (simulator counts from zero, embedded uses `loop.time()`); a relative delay keeps
  that out of protocol code. Every current call site is already
  `schedule_timer(tag, current_time() + interval)`.
- **`CancelTimer` cancels every timer with that tag.** Timers carry no handle — a command is
  fire-and-forget and cannot return one — so the tag is the only identity a timer has. This
  is the semantics `IProvider.cancel_timer` always documented and gradysim always implemented.
- **`tracked_variables` became `TrackVariable(name, value)`.** A mutable dict whose
  `__setitem__` had side effects was an action wearing a data structure's clothing.

### `Provider` — the deliberate exception

`Provider` (`node_id()`, `now()`, `wall_time()`) is the one surface that is neither command
nor event. Rationale: a command is fire-and-forget and cannot return a value, so modelling
"what time is it" as a command would require inventing a request/response event pair for
every read. Anything that *acts* on the world is a command; only synchronous queries live
here. `now()` is node-local monotonic with an unspecified epoch (differences only, never
comparable across nodes); `wall_time()` is the cross-node-comparable clock.

### Dispatch (`bus.py`)

Handlers are ordered by `(priority, seq)` ascending — lower priority first, ties FIFO by
registration order.

| band | value | for |
|---|---|---|
| `PRIORITY_OBSERVER` | −300 | statistics/tracing; contractually must return `CONTINUE` |
| `PRIORITY_PLUGIN` | 0 | plugins (default) |
| `PRIORITY_PROTOCOL` | 100 | the protocol's own handlers |

- `Disposition.STOP` consumes the event; `CONTINUE` or `None` passes it on.
- `StartEvent`/`StopEvent` **ignore `STOP`**, so one plugin cannot skip another's setup or
  teardown. Mirrors the old `register_initialize`/`register_finish`, which had no
  `DispatchReturn` support at all.
- Dispatch walks `type(event).__mro__`, so subscribing to a base event class receives
  subclasses.
- Dispatch iterates a **snapshot**, so a handler may subscribe or cancel mid-dispatch — the
  `random_mobility` plugin does exactly this, and plugins are constructed from inside a
  `StartEvent` handler.
- `Subscription.cancel()` is idempotent; the legacy dispatcher raised `ValueError` on a
  second unregister.

Two intentional behavioural changes relative to the old dispatcher, both belonging in a
changelog: **tie-break is now FIFO** (the old `insert(0, handler)` made it LIFO by accident —
no in-tree plugin depends on it, since each filters by tag or prefix and passes everything
else through), and the Start/Stop non-interruptibility above.

### Wiring (`host.py`)

```python
runtime = Runtime(MyHost())
protocol = runtime.install(SweepProtocol)   # capability check happens here
runtime.start()                             # delivers StartEvent
runtime.deliver(PacketEvent("hello", source=2))   # the ONLY publish path
runtime.stop()                              # delivers StopEvent, then closes
```

`install()` calls `host.register_commands(registry)`, recovers the protocol's declared
command union by walking `cls.__mro__` → `__orig_bases__` → `get_args`, and raises
`UnsupportedCommandError` naming the missing commands **before the protocol runs** — not on
first dispatch, hours into a flight. `CommandRegistry` resolves through the command's MRO, so
a host may register one handler for `MobilityCommand` and service every subclass.

Protocols are constructed with a plain `cls()`. The `instantiate(provider)` classmethod
survives only in `legacy.py`. `start()`/`stop()` are idempotent; `deliver()` before install
or after stop is a silent no-op.

### Legacy emulation (`legacy.py`)

`legacy(MyOldProtocol)` returns a generated `LegacyProtocolAdapter` subclass (memoised per
class, so `declared_commands` is stable) that installs like any other protocol. It:

- re-declares `IProtocol`/`IProvider`/`Telemetry`/`MobilityCommand`/`CommunicationCommand`
  byte-compatibly so old imports keep resolving and type-checking;
- constructs the old protocol via `instantiate()` (subclasses are allowed to override it);
- routes the four legacy provider calls through `adapter.send`, so legacy protocols are
  subject to the **same registry and capability check** as native ones;
- converts absolute `schedule_timer(tag, timestamp)` into `ScheduleTimer(tag, timestamp - now())`;
- turns `tracked_variables[k] = v` into `TrackVariable(k, v)` via a dict subclass;
- subscribes all five handlers at `PRIORITY_PROTOCOL` and returns `None` from each, so
  new-world plugins can sit in front of a legacy protocol;
- **drops `PacketEvent.source`**, because `handle_packet(message: str)` has nowhere to put
  it. That is the fidelity the adapter promises and the stated reason to migrate.

It also fixes the `SendMessageCommand` equality defect by calling `super().__init__`.

---

## 4. The typing encoding — the heart of the review

The user's requirement is that a protocol declares its event and command sets and that
out-of-set use is a **static** error. The encoding:

```python
EventT = TypeVar("EventT", bound=Event,   contravariant=True)
CmdT   = TypeVar("CmdT",   bound=Command, contravariant=True)
_E     = TypeVar("_E",     bound=Event)      # invariant

class Protocol(Generic[EventT, CmdT]):
    provider: Provider
    def send(self, command: CmdT) -> None: ...

def subscribe(
    protocol: Protocol[_E, Any],                      # contravariance ⇒ _E <: declared union
    event:    type[_E],                               # lower bound
    handler:  Callable[[_E], Optional[Disposition]],  # upper bound
    priority: int = PRIORITY_PLUGIN,
) -> Subscription: ...
```

Contravariance is what makes *set membership* expressible: `Protocol[A|B|C]` is a subtype of
`Protocol[A]` exactly because `A` is a subtype of `A|B|C` and the flip reverses it. The three
argument constraints on `subscribe` admit one solution for `_E`, which must lie inside the
declared union.

Four consequences a reviewer should hold onto:

1. **`subscribe` must be a module-level function, not a method.** The `self`-annotation form
   (`def subscribe(self: Protocol[_E, Any], ...)`) was proposed first and **does not work** on
   either checker: both bind the self-type first and freeze `_E` to the entire declared union,
   so the handler never narrows and the *legitimate* case errors. As a function all three
   arguments are solved jointly. Side benefit: protocols and plugins now use the literally
   identical call.
2. **Nothing in the interface may return `EventT` or `CmdT`.** Both checkers reject a
   contravariant type variable in return position. This is why there is no `emit`, no
   `next_event`, and why `Runtime.install` returns `Any`.
3. **`EventT` is referenced nowhere but `Generic[EventT, CmdT]`.** After `emit` was cut at the
   user's request, the parameter became phantom. Subtyping for nominal generics comes from
   *declared* variance, so the guarantee survives — but this was re-verified from scratch
   ("Gate #1" below) precisely because a naive re-test that left `EventT` in a base-class list
   would have falsely passed.
4. **Subtypes yes, supertypes no.** You may subscribe to a declared type or any *subtype* of
   it, never a supertype. Declaring `TelemetryEvent` does not entitle you to everything; a
   genuine catch-all observer declares `Event` itself. This asymmetry is deliberate,
   documented, and covered by `tests/static/positive.py::CatchAll`.

Capabilities fall out for free, on both sides:

```python
# install-time, by name, before the protocol runs
UnsupportedCommandError: SweepProtocol declares command(s) SetGimbal but host
  EmbeddedHost registered no handler for them.

# edit-time, at the plugin construction site — contravariance again
class MissionPlugin:
    def __init__(self, protocol: Protocol[TelemetryEvent, GotoCoords | SetSpeed]) -> None: ...
```

That plugin signature replaces Raft's runtime duck-typing
(`required_methods = ["send_communication_command", ...]`) with a type error at the call site.

**Known ergonomic wart:** mypy's message for a membership violation is
`Cannot infer value of type parameter "_E"` — poor. Pyright's is precise. Both the README and
`tests/static/negative.py` spell out the mapping. The plan called for keeping a *runtime*
check purely for message quality; **this was not implemented** (see §6).

---

## 5. Verification — what was actually run

I re-ran all three gates independently while preparing this brief:

```
pytest    35 passed
mypy      Success: no issues found in 13 source files   (strict, --warn-unused-ignores, py3.10)
pyright   0 errors, 0 warnings, 0 informations          (strict, reportUnnecessaryTypeIgnoreComment)
```

`./check.sh` runs all three. Note it assumes `mypy`/`pyright`/`pytest` are importable from the
active interpreter; in this workspace they live in a session scratchpad plus `.lac_env`, so a
bare `./check.sh` fails on missing modules rather than on any code defect.

The **static suites are the primary contract**, not an afterthought:

- `tests/static/positive.py` must produce **zero** diagnostics. A finding there is a false
  positive — the encoding rejecting legitimate code. Covers: exact handler match, default and
  explicit priority, lambda handlers, a handler annotated *wider* than the subscribed event,
  user-defined event hierarchies, base-class subscription, `Protocol[Event, ...]` catch-all,
  plugin-superset acceptance, and command-family declaration.
- `tests/static/negative.py` annotates every expected failure with `# type: ignore[<code>]`
  and runs under `--warn-unused-ignores`. The pass condition is again **zero output**, so an
  error that stops firing surfaces as an unused ignore. The guarantee cannot quietly go
  vacuous. Non-vacuity was confirmed by stripping suppressions and watching each error
  reappear on both solver paths (`[misc]` for membership, `[arg-type]` for handler mismatch
  and plugin-superset violations).
- **Both checkers are run and both versions are pinned** (mypy 2.3.0, pyright 1.1.411). They
  disagreed on three of the five encodings tried during design; a single checker would have
  shipped a broken guarantee. Treat a version bump as an API-affecting change.

Runtime coverage (35 tests): priority ordering and FIFO tie-break, `STOP` truncation,
Start/Stop ignoring `STOP` and being idempotent, subscribe/cancel during dispatch, cancel
idempotence, MRO dispatch to base subscribers, timer ordering / duplicate tags / cancel-all /
non-positive delay, `declared_*` over direct, non-union and grandchild parameterizations,
capability-check failure text, send-before-install error, registry MRO resolution, provider
clocks, deliver-after-stop. Legacy coverage (15 tests): command translation both families,
absolute→relative timer conversion, source-dropping, `Telemetry` re-wrapping, `finish()` on
stop, `legacy()` idempotence, the fixed equality defect, and that the capability check applies
to legacy protocols too.

**"Gate #1"** deserves separate mention. When the user cut `emit`, `EventT` stopped being used
anywhere but `Generic[...]`. Rather than assume the guarantee survived, the encoding was
rebuilt from scratch in that exact shape and the full matrix re-run on both checkers before
the library was written. It passed with no phantom member needed.

---

## 6. Deviations from the approved plan, and known gaps

Listed so the reviewer doesn't have to rediscover them, and because two are arguably defects.

1. **`testing.py`'s module docstring claims a conformance suite that does not exist.** It
   reads "plus the conformance suite every real host must pass"; the module contains only
   `FakeHost` and `install()`. The plan described this suite as *the* mechanism preventing the
   two runtimes from drifting apart again, and as the contract handed to the gradysim side
   (which cannot be built here). This is a real gap plus a false docstring.
2. **The event bus is created eagerly in `Protocol.__init__`, not lazily.** The plan called
   for lazy creation "so a protocol forgetting `super().__init__()` still works". As shipped,
   forgetting `super().__init__()` yields an `AttributeError` on the first `subscribe`, not a
   clear error. Worth deciding: lazy creation, or an explicit diagnostic.
3. **No runtime membership check.** The plan kept one specifically to compensate for mypy's
   poor `Cannot infer value of type parameter "_E"` message. Not implemented; the mitigation
   is documentation only.
4. **`Runtime.install` is typed `(cls: type) -> Any`.** Both ends lose typing — the parameter
   accepts any class, and the return is `Any`. A `TypeVar` bound to `Protocol[Any, Any]` would
   recover the return type; the parameter is harder given `legacy()` returns a generated class.
5. **`Protocol.bus` and `Protocol.command_sink` are public attributes**, documented as
   library-internal. Underscored names tripped pyright strict's `reportPrivateUsage` at every
   `subscribe`/`Runtime` call site, and the rename was chosen over suppressing the rule. It
   does mean the internals are reachable and unenforced.
6. **`PRIORITY_DECODER` (−200) was dropped**, correctly following from the removal of `emit` —
   without `emit`, a decoder cannot republish a typed event. The consequence is that Raft and
   `follow_mobility` must keep string-prefix filtering with `STOP` rather than becoming typed
   demultiplexers. This is a real cost of the "no emit" decision, and worth confirming the
   user accepts it.
7. **Not yet built, in the intended order:** the five plugins (`mission_mobility`,
   `follow_mobility`, `random_mobility`, `statistics`, `raft`) into `gradys_core.plugins`;
   `EmbeddedHost` + `Runtime` wiring + the two `source`-plumbing one-liners in gradys-embedded;
   migration of `embedded_experiments`.
8. **`GradysimHost` cannot be built on this machine.** The gradysim repo is not present
   (`/home/fleury/gradys/major_projects/` does not exist); its interface was read from GitHub.
   The `Host` ABC plus the (missing) conformance suite is the contract handed across.
9. **`interface_example/poc.md`** appeared in the workspace mid-session and is empty. It is
   unrelated to this tree and was left alone.
10. **Nothing is committed.** `git init` ran; the tree is entirely untracked.

---

## 7. What I would most like challenged

- **Does the membership guarantee actually hold**, on both checkers, for cases the static
  suites do not cover? Specifically: generic protocol subclasses; a protocol parameterized
  with a `TypeAlias` defined in another module; `Union[...]` spelled long-form vs `X | Y`;
  a protocol whose declared set is a single non-union type; diamond inheritance across two
  parameterized bases. `declared_*` returns `()` on a shape it cannot parse, which would make
  the capability check **silently vacuous** rather than loud.
- **Is `EventT` being phantom actually safe long-term**, or does it depend on current checker
  behaviour that a version bump could change? The suites would catch a regression, but only
  if someone runs them.
- **Is the "no emit / no decoder" model right** for Raft-style protocols that genuinely want
  to demultiplex one `PacketEvent` into typed domain events?
- **Is cancel-all-by-tag the right timer semantics** now that timers are handle-less commands,
  or does the loss of per-occurrence cancellation bite a real protocol?
- **Is the legacy adapter faithful enough?** It silently drops `PacketEvent.source` and
  converts absolute timestamps using `now()` at call time. Are there old protocols whose
  behaviour that changes?
- **Ordering changes**: FIFO tie-break and non-interruptible Start/Stop are intentional, but
  they are behaviour changes to existing plugins. Is either load-bearing somewhere I missed?
