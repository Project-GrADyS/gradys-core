# Interface drafts

Exploratory sketches of alternative gradys-core environment seams. **Not working
library code** — each file is a runnable pitch of one idea:

```bash
python interface_drafts/v1_host.py      # Host seam,   thiago's decorator authoring style
python interface_drafts/v2_linker.py    # linker seam, thiago's decorator authoring style
python interface_drafts/v3_host_core.py   # Host seam,   main-library authoring style
python interface_drafts/v4_linker_core.py # linker seam, main-library authoring style
```

The drafts pair up so the two questions can be judged independently: **v1 ↔ v3** are the
same Host seam and **v2 ↔ v4** are the same linker seam, differing only in authoring
surface. v1/v2 use the decorator style from `src/gradys_core/thiago_protocol.py`
(`@subscribe(Event)` methods, `attr = command(C)`, requirements derived from usage
sites); v3/v4 import the real `gradys_core` and keep its authoring surface
(`Protocol[Events, Commands]`, `subscribe(self.provider, Event, handler)` in
`on_bind()`, `self.provider.send(cmd)`).

## Shared authoring surface

In both drafts the user never declares event/command sets manually. Requirements are
derived from usage sites and collected by `__init_subclass__`:

```python
class SweepProtocol(Protocol):
    move = command(Move)                     # outgoing command, callable as self.move(...)

    @subscribe(Start)                        # decorator replaces subscribe(provider, ...)
    def on_start(self, event: Start) -> None:
        self.move(10.0, 20.0, 30.0)
```

## `v1_host.py` — hosted version

The environment seam is a `Host` with exactly three methods:

| Method | Role |
|---|---|
| `register_listener(CommandType, fn)` | environment provides the executor for each command it supports |
| `bind(UserProtocolSubclass)` | checks requirements against capabilities, instantiates, wires handlers |
| `deliver(event)` | pushes an event into the bound protocol's `@subscribe` handler |

`bind` raises `RuntimeError` if the protocol requires an event the host cannot produce
or a command with no registered listener.

## `v2_linker.py` — no Host, `bind` as a C-linker analog

There is no Host object at all; gradys-embedded and gradys-sim NG manipulate the
`Protocol` class directly. The seam is `Protocol.bind(table)` where `LinkTable` is the
environment's symbol table: supported events as *blank slots*, supported commands with
*implementations already provided*. `bind` fills the event slots with the user's
handlers and links `command()` attributes to the provided implementations; any
requirement missing from the table is an undefined symbol → `RuntimeError`. After
linking, the environment owns the loop and calls the slots directly:

```python
table.events[Telemetry](Telemetry(1.0, 2.0, 3.0))
```

## `v3_host_core.py` — hosted seam over the main implementation

Same three-method `Host` interface as v1 (`register_listener` / `bind` / `deliver`), but
implemented as a thin wrapper composing existing core pieces instead of new dispatch
code: `CommandRegistry` backs the listeners, `Host.bind` builds a `Provider` from the
registry's `dispatch`/`supports` callables, calls core `bind()` (which runs the command
capability gate before construction) and `Binding.start()` (StartEvent first), and
`Host.deliver` forwards to `Binding.deliver`. The host adds one check core doesn't have:
declared *events* against the events this host can produce.

## `v4_linker_core.py` — linker seam over the main implementation

Same `LinkTable` idea as v2 (blank event slots, provided command impls, undefined
symbols → `RuntimeError`), with `link(cls, table)` standing in for `Protocol.bind`
(core's `Protocol` is untouched). One deliberate difference from v2: a filled slot is
the *delivery path* (`Binding.deliver`), not the user's bare handler — so the real bus
stays in play and subscriptions, priorities, cancellation and the lifecycle window all
keep working. Slots for events the protocol didn't declare stay `None`.

## Known tradeoff

The main library keeps `subscribe(provider, event, handler)` as a module-level function
because (verified on pinned mypy/pyright — see README §“Why `subscribe` is a function”)
no decorator or method form gives both static event-set membership *and* narrowly-typed
handlers. Drafts v1/v2 deliberately trade that away: membership checking moves entirely
to runtime `bind()`, in exchange for a declaration-free authoring surface. Drafts v3/v4
keep the static guarantees, so they only explore the seam question.
