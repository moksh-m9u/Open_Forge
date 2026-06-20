# net_assigner.py — None normalized_function Handling Analysis

## Context

`PinDefinition.normalized_function` is `Optional[str] = None` in `src/schemas/datasheet.py`.
It is set by P2 Phase 2 (pin normalization pipeline). If P2 has not run on a component,
every one of its pins will have `normalized_function = None`.

`net_assigner.py` reads `normalized_function` in two public functions and one helper.

---

## Behaviour per function

### `assign_power_nets` (lines 161–171)

```python
for ref, datasheet, pin in pin_data:
    func = pin.normalized_function
    if func == "POWER_POSITIVE":
        ...
    elif func == "POWER_GROUND":
        ...
    elif func == "POWER_INPUT":
        ...
```

When `func` is `None`, it matches none of the three branches.
**Result: silent skip. No log, no flag, no error.**

### `assign_protocol_nets` (lines 218–219)

```python
func = pin.normalized_function
if func in SKIP_FUNCTIONS or func is None:
    continue
```

`SKIP_FUNCTIONS` (lines 19–25) explicitly contains `None`:

```python
SKIP_FUNCTIONS = frozenset({
    None,
    "NO_CONNECT",
    "POWER_POSITIVE",
    "POWER_GROUND",
    "POWER_INPUT",
})
```

So `func in SKIP_FUNCTIONS` is already `True` when `func is None`.
The `or func is None` guard is **redundant** but harmless.
**Result: `continue` — silent skip. No log, no flag, no error.**

### `_pin_ref` (lines 85–87)

```python
def _pin_ref(ref: str, pin: PinDefinition) -> PinRef:
    pin_name = pin.normalized_function or pin.raw_name
    return PinRef(ref=ref, pin_name=pin_name, pin_number=pin.pin_number)
```

Falls back to `raw_name` when `normalized_function` is `None`.
However, `_pin_ref` is only called *after* a pin passes the function-matching logic above,
so a pin with `normalized_function = None` never reaches this function.
The fallback is **dead code** for the None case.

---

## Summary

| Function | None behaviour | Raises? | Wrong net? |
|---|---|---|---|
| `assign_power_nets` | Silent skip (no branch matches) | No | No |
| `assign_protocol_nets` | Silent skip (`continue`) | No | No |
| `_pin_ref` | Fallback to `raw_name` (unreachable for None pins) | No | N/A |

No crash. No wrong net assignment. **Silent skip in both paths.**

---

## The Real Problem: Untracked Pin Loss

`_iter_pins` appends to `unresolved_pins` when a *datasheet* is `None`:

```python
if datasheet is None:
    logger.warning("Skipping component %s — no datasheet available", ref)
    if unresolved_pins is not None:
        unresolved_pins.append(PinRef(ref=ref, pin_name="UNKNOWN", pin_number="?"))
    continue
```

There is **no equivalent mechanism** for pins with `normalized_function = None`.
A pin skipped due to missing normalization:
- does not appear in `unresolved_pins`
- does not trigger a `logger.warning`
- does not generate a `ReviewFlag` in the NIR

If P2 has not run on a component, **all of its pins are silently dropped from the netlist**.
The NIR produced downstream will be missing those connections with no indication that
anything was omitted.

---

## Recommendation

Add a warning and `unresolved_pins` entry for pins skipped due to `None` normalization,
parallel to the existing datasheet-missing guard:

```python
# In assign_power_nets and assign_protocol_nets, inside _iter_pins loop or inline:
for ref, datasheet, pin in pin_data:
    if pin.normalized_function is None:
        logger.warning(
            "Pin %s.%s has no normalized_function — P2 may not have run; skipping",
            ref, pin.pin_number
        )
        if unresolved_pins is not None:
            unresolved_pins.append(
                PinRef(ref=ref, pin_name=pin.raw_name, pin_number=pin.pin_number)
            )
        continue
```

This would surface missing normalization as a `ReviewFlag` in the NIR rather than
causing silent netlist gaps.
