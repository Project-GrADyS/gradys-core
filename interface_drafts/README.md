# Interface drafts

Exploratory sketches of an alternative gradys-core interface, evolving the ideas in
`src/gradys_core/thiago_protocol.py` / `thiago_com_provider.py`. **Not working library
code** — each file is a self-contained, runnable pitch of one idea:

```bash
python interface_drafts/v1_host.py
python interface_drafts/v2_linker.py
```

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

## Known tradeoff

The main library keeps `subscribe(provider, event, handler)` as a module-level function
because (verified on pinned mypy/pyright — see README §“Why `subscribe` is a function”)
no decorator or method form gives both static event-set membership *and* narrowly-typed
handlers. These drafts deliberately trade that away: membership checking moves entirely
to runtime `bind()`, in exchange for a declaration-free authoring surface.
