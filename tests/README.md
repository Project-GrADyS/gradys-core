# Test map

Every file tests **one contract**, named in its module docstring. Shared example
protocols/hosts live in `support.py` (each documents what it exercises); fixtures in
`conftest.py` (`host` = fresh FakeHost, `bound` = bind+start on it).

| file | contract |
|---|---|
| `test_bus.py` | dispatch semantics: priority bands, FIFO ties, `STOP`, MRO matching, mutation during dispatch |
| `test_protocol.py` | the protocol-author surface: provider queries, `send`, runtime backstops, `on_bind` timing, no-super rule |
| `test_binding.py` | the environment seam: capability gate, declared-set introspection, one-provider-per-protocol, lifecycle ordering, timer round-trips |
| `test_legacy.py` | legacy emulation fidelity (source dropped, absolute→relative timers, same capability gate) |
| `test_conformance.py` | FakeHost passes the `HostConformance` suite it hands to real environments |
| `static/` | the **static guarantees** — see below |

## Running the gates

All three must pass (`../check.sh` runs them):

```bash
python -m pytest tests/ -q
python -m mypy                                   # strict, --warn-unused-ignores
python -m pyright --pythonpath "$(command -v python)"
```

**Both checkers are pinned and both must run.** They disagreed on three of the five
encodings tried during design; one checker alone can ship a broken guarantee. Treat a
version bump as an API-affecting change.

## The static suites (`static/positive.py`, `static/negative.py`)

These are the *primary contract*, not an afterthought. The pass condition for both is
**zero checker output**:

- A diagnostic in `positive.py` is a false positive — the encoding rejecting
  legitimate code.
- `negative.py` suppresses every expected error with `# type: ignore[<code>]` and runs
  under `--warn-unused-ignores`, so an error that *stops firing* surfaces as an unused
  ignore. The guarantees cannot quietly become vacuous.

The numbered guarantees, cross-referenced by the `G*` labels in both files:

| # | guarantee | violation surfaces as (mypy) | runtime backstop |
|---|---|---|---|
| G1 | `subscribe` event must be in the declared event set | `[misc]` "Cannot infer value of type parameter \_E" | `UndeclaredEventError` at subscribe time |
| G2 | handler parameter must accept the subscribed event | `[arg-type]` | — |
| G3 | `provider.send` command must be in the declared command set | `[arg-type]` | `UnsupportedCommandError` at send time |
| G4 | a plugin's `Provider[...]` parameter is a capability requirement; supersets accepted, gaps rejected at the wiring site | `[arg-type]` | capability gate at `bind()` |
| G5 | subscribe to a declared type or a *subtype*; never a supertype (catch-alls declare `Event` itself) | `[misc]` | `UndeclaredEventError` |

G1's mypy message is genuinely poor — that *is* the membership failure. Pyright reports
the same violation precisely, and the runtime backstop names the declared set.

## Why the setup looks the way it does

- `FakeHost` builds a real `Provider` from a `CommandRegistry` and injects it via
  `bind()` — the exact wiring a real environment uses, so tests exercise the true
  seam, not a shortcut.
- Protocols in `support.py` keep plain `__init__` methods (no `super().__init__()`)
  and subscribe in `on_bind()` — the base class is stateless and the provider only
  exists after `bind()` injects it.
- Capability-gate tests use `PoorHost`/`FamilyHost` subclasses that override
  `register_commands` — capability is a property of the *environment*, so the tests
  vary the environment, never the protocol.
