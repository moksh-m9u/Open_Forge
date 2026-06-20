# Field Trace: PinDefinition.normalized_function

## Definition

**File:** `src/schemas/datasheet.py` line 193
```python
normalized_function: Optional[str] = Field(
    default=None,
    description="Normalized net name set by P2 Phase 2 — None until normalized",
)
```
Default is `None`. It is `None` on every pin that comes out of Phase 1 extraction
and remains `None` for any pin that fails all three normalization tiers in P2.

---

## Where It Is Set

### 1. Phase 1 extraction — always None
**File:** `src/datasheet/phase3_extract/__init__.py` line 201

```python
# Rule 3: PinDefinition.normalized_function is None by default
```
Phase 1 writes `PinDefinition` objects with `normalized_function` left at its
schema default (`None`). This is intentional — normalization is a separate step.

### 2. Pin normalizer (P2) — sets value or leaves None
**File:** `src/knowledge_graph/pin_normalizer/normalizer.py`

Three-tier process per pin (`_normalize_single_pin`, lines 32–61):
1. Dictionary lookup — confidence 1.0
2. Context resolution — confidence 0.90
3. LLM fallback — variable confidence

If any tier succeeds (`canonical is not None`), the pin is updated (line 96–99):
```python
new_pin = pin.model_copy(update={
    "normalized_function": canonical,
    "normalization_confidence": confidence,
})
```

If all tiers fail (line 107–115):
```python
new_pin = pin.model_copy(update={
    "normalized_function": None,
    "normalization_confidence": confidence,  # Usually 0.0
})
# review_flag added to parent datasheet, logger.warning emitted
```

Normalization failures are tracked: a review flag string is appended to
`datasheet.review_flags` and a `logger.warning` is emitted. However, no
`ReviewFlag` object is written into the NIR at this stage — that is left to
downstream consumers.

---

## Where It Is Read

### Reader 1: p1_importer.py — `_create_pin_nodes`
**File:** `src/knowledge_graph/importers/p1_importer.py` lines 111–113

```python
if pin.normalized_function is not None:
    properties["normalized_function"] = pin.normalized_function
```

**None:** Field is omitted from `KGNode.properties`. Key is absent from the dict.
**Value:** Stored in properties dict.

**Handles None?** ✅ Yes — explicit `is not None` guard. Omission is correct;
KG consumers must treat a missing key as "not yet normalized".

---

### Reader 2: net_assigner.py — `_pin_ref`
**File:** `src/schematic/net_assigner.py` line 86

```python
pin_name = pin.normalized_function or pin.raw_name
```

**None:** Falls back to `raw_name`.
**Value:** Uses the normalized function name.

**Handles None?** ✅ Yes — `or` fallback. However, `_pin_ref` is only called
*after* a pin has already passed function-matching in `assign_power_nets` or
`assign_protocol_nets`, where `None` pins are skipped. So this fallback is
**dead code for the None case** in practice — a None pin never reaches `_pin_ref`.

---

### Reader 3: net_assigner.py — `assign_power_nets`
**File:** `src/schematic/net_assigner.py` lines 161–171

```python
func = pin.normalized_function
if func == "POWER_POSITIVE":
    ...
elif func == "POWER_GROUND":
    ...
elif func == "POWER_INPUT":
    ...
```

**None:** Matches no branch. Pin is silently skipped — not added to any net,
not added to `unresolved_pins`, no warning logged.
**Value:** Routed to the matching power net.

**Handles None?** ⚠️ Partially — no crash, but the skip is **silent and untracked**.
If a power pin fails normalization, it disappears from the netlist with no signal.

---

### Reader 4: net_assigner.py — `assign_protocol_nets`
**File:** `src/schematic/net_assigner.py` lines 217–219

```python
func = pin.normalized_function
if func in SKIP_FUNCTIONS or func is None:
    continue
```

`SKIP_FUNCTIONS` already contains `None`, making `or func is None` redundant.

**None:** `continue` — pin silently skipped.
**Value:** Enters function-matching logic for shared/unique/UART protocol nets.

**Handles None?** ⚠️ Partially — no crash, correct skip, but **silent and untracked**.
Same gap as Reader 3.

---

### Reader 5: erc.py — `_pin_lookup`
**File:** `src/schematic/erc.py` line 39

```python
lookup[(ref, pin.pin_number)] = (pin.pin_type or "", pin.normalized_function)
```

**None:** Stored as `None` in the lookup tuple `(pin_type, None)`.
**Value:** Stored as the string value.

**Handles None?** ✅ Yes — the tuple value is typed `str | None` (line 34),
and all call sites that retrieve `func` from this lookup handle `None` correctly
(see Readers 6 and 7 below). No crash.

---

### Reader 6: erc.py — `power_net_has_source` rule
**File:** `src/schematic/erc.py` line 83–85

```python
_pin_type, func = pin_lookup.get((conn.ref, conn.pin_number), ("", None))
if func == "POWER_POSITIVE" or "regulator" in conn.ref.lower():
    has_source = True
```

**None:** `None == "POWER_POSITIVE"` is `False`. Falls through to the
`"regulator" in conn.ref.lower()` check. Pin contributes nothing to source
detection via function.
**Value:** Equality check fires correctly.

**Handles None?** ✅ Yes — equality comparison with None is always False in Python,
so the logic degrades gracefully. A power pin whose `normalized_function` is `None`
will not be recognised as a source, which may produce a false-positive
`power_net_has_source` CRITICAL violation. This is a **semantic gap**, not a crash.

---

### Reader 7: erc.py — `no_required_pin_floating` rule
**File:** `src/schematic/erc.py` lines 101–112

```python
func = pin.normalized_function
if func not in _REQUIRED_FUNCTIONS:
    continue
```

`_REQUIRED_FUNCTIONS = frozenset({"POWER_POSITIVE", "POWER_GROUND", "ENABLE", "RESET"})`

**None:** `None not in _REQUIRED_FUNCTIONS` is `True` → `continue`. Pin is skipped.
**Value:** Checked against the required set; if present, floating check runs.

**Handles None?** ✅ Yes — no crash. However there is a **semantic gap**: a required
pin (e.g. POWER_GROUND) that failed normalization will have `normalized_function=None`,
be skipped here, and **not be flagged as floating** even if it is unconnected.
A genuinely dangerous floating power pin can pass the ERC silently.

---

### Reader 8: erc.py — `no_floating_inputs` rule
**File:** `src/schematic/erc.py` lines 137–138

```python
pin_type, func = pin_lookup.get((conn.ref, conn.pin_number), ("", None))
if func in _POWER_FUNCTIONS:
    continue
```

**None:** `None in _POWER_FUNCTIONS` is `False` → does not skip. Pin proceeds
into floating-input detection based on `pin_type` alone.
**Value:** Power pins are skipped, others proceed.

**Handles None?** ✅ Yes — no crash. The rule uses `pin_type` (not `func`) for
the floating-input decision, so a `None` normalized_function here causes no
false result in this rule specifically.

---

## Summary Table

| File | Location | None behaviour | Crash? | Untracked? | Semantic gap? |
|---|---|---|---|---|---|
| `normalizer.py` | **WRITER** — sets None on failure | Adds review_flag to datasheet | — | — | — |
| `p1_importer.py` | `_create_pin_nodes` | Key omitted from KGNode.properties | No | No | No |
| `net_assigner.py` | `_pin_ref` | Falls back to `raw_name` (dead code path) | No | No | No |
| `net_assigner.py` | `assign_power_nets` | ⚠️ Silent skip, no unresolved_pins entry | No | **Yes** | **Yes** — power pins lost from netlist |
| `net_assigner.py` | `assign_protocol_nets` | ⚠️ Silent skip, no unresolved_pins entry | No | **Yes** | **Yes** — signal pins lost from netlist |
| `erc.py` | `_pin_lookup` | Stored as None in tuple (typed correctly) | No | No | No |
| `erc.py` | `power_net_has_source` | Pin not recognised as source | No | No | **Yes** — may produce false CRITICAL violation |
| `erc.py` | `no_required_pin_floating` | Pin skipped by `not in` check | No | No | **Yes** — floating required pin not flagged |
| `erc.py` | `no_floating_inputs` | Pin not skipped as power; uses pin_type only | No | No | No |

---

## Flagged Cases (None not fully handled)

### FLAG 1 — net_assigner.py `assign_power_nets` and `assign_protocol_nets`
Both silently drop pins with `normalized_function=None` from the netlist with
no `unresolved_pins` entry, no `logger.warning`, and no `ReviewFlag`. If P2
normalization fails on a power pin, that pin's net will be missing from the NIR.

### FLAG 2 — erc.py `power_net_has_source`
A regulator's VCC output pin with `normalized_function=None` will not be
identified as a power source by function name. This can trigger a false
CRITICAL `power_net_has_source` violation on a correctly designed board.

### FLAG 3 — erc.py `no_required_pin_floating`
A floating power or enable pin that failed normalization will have
`normalized_function=None`, causing it to be skipped by the
`not in _REQUIRED_FUNCTIONS` check. The ERC will **miss a genuine fault**.
This is the most safety-critical of the three gaps.
