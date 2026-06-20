# Footprint Translation Gap Analysis
## builder.py → tscircuit_serializer.py

## The Translation Layer

One translation step exists between `builder.py` and the TSX output:
`resolve_footprint()` in `src/output/tscircuit_footprint_map.py`,
called by `tscircuit_serializer.py` at line 105–108.

```python
footprint, fp_needs_review = resolve_footprint(
    component.footprint, component.component_type
)
```

---

## What resolve_footprint Does

```python
def resolve_footprint(ipc_name: str, component_type: str) -> tuple[str, bool]:
```

Three resolution paths, in order:

1. **Passive type + Imperial size** — if component is resistor/capacitor/inductor
   and `ipc_name` is one of `0402/0603/0805/1206`, constructs
   `R_0402_1005Metric`, `C_0603_1608Metric`, etc. Returns `needs_review=False`.

2. **`TSCIRCUIT_FOOTPRINT_MAP` lookup** — 27-entry dict of known IPC-7351 names
   to tscircuit registry names. Returns mapped name, `needs_review=False`.

3. **Pass-through fallback** — if neither path matches:
   `return ipc_name, True`
   The raw input string is returned unchanged with `needs_review=True`.

---

## What Happens with an Unrecognised String

`tscircuit_serializer.py` handles `needs_review=True` like this (lines 111–115):

```python
if fp_needs_review:
    unresolved_footprints.append(f"{component.ref} ({component.footprint})")
```

And after all components are processed (lines 143–144):

```python
for item in unresolved_footprints:
    logger.warning("Unresolved tscircuit footprint: %s", item)
```

The raw unrecognised string is then written verbatim into the TSX (line 120):

```python
props = f'name="{component.ref}" footprint="{footprint}"'
```

**Result:** The TSX file is written with `footprint="<raw datasheet string>"`.
The tscircuit runtime will either fail silently on that component or render it
with no footprint geometry. No exception is raised. The export is not blocked.
`TSCircuitOutput.success` is still set to `True`.

---

## The Upstream Gap: builder.py Has No Validation

In `src/nir/builder.py` (line 69):

```python
footprint=matching.package if matching is not None else "UNKNOWN",
```

`datasheet.package` is copied directly into `ComponentRef.footprint` with no
validation. The schema docstring on `ComponentDatasheet.package` says:

> "Must be one of: SOT-23-5, SOT-23-3, SOIC-8, SOIC-16, QFN-16, 0402, 0603,
> 0805, DIP-8, TO-220, TSSOP-8, etc."

However this is a **comment, not a Pydantic constraint** — no `Literal`, no
`field_validator`, no enum. Any string the datasheet extractor produces is
accepted and flows downstream unchecked.

---

## Full Data Flow

```
datasheet.package
  (any string — no Pydantic enforcement, comment-only constraint)
        │
        ▼  builder.py line 69
ComponentRef.footprint
  (copied as-is)
        │
        ▼  tscircuit_serializer.py line 105–108
resolve_footprint(component.footprint, component.component_type)
        │
        ├─ passive + size match  ──► correct tscircuit name, needs_review=False
        ├─ TSCIRCUIT_FOOTPRINT_MAP hit ─► correct tscircuit name, needs_review=False
        └─ no match  ────────────► raw string passed through, needs_review=True
                                     logger.warning() emitted
                                     ref added to unresolved_footprints
                                     raw string written verbatim into TSX
                                     tscircuit runtime: broken / blank footprint
                                     TSCircuitOutput.success = True (not blocked)
```

---

## Risk Assessment

| Scenario | Outcome |
|---|---|
| Known IPC name (SOT-23-5, 0402, etc.) | Correctly translated |
| Passive size without type suffix (e.g. raw "0402" for IC) | Passive path may misfire if component_type is not "resistor/capacitor/inductor" — falls through to map lookup, finds "R_0402_1005Metric", which is wrong for an IC |
| Unknown string (e.g. "SC-70-5", "LFCSP-16", "TO-252") | Pass-through, warning logged, broken TSX footprint |
| `"UNKNOWN"` (no matching datasheet) | Pass-through, warning logged, broken TSX footprint |

---

## Recommendations

1. **Add a Pydantic `field_validator` to `ComponentDatasheet.package`** that rejects
   strings not in the known IPC-7351 set at extraction time, catching the problem
   before it enters the KG or NIR.

2. **Set `TSCircuitOutput.success = False`** (or at minimum add a `ReviewFlag` to the
   NIR) when `unresolved_footprints` is non-empty, so the broken export is not
   silently treated as successful.

3. **Guard the passive pass in `resolve_footprint`** — currently a raw `"0402"` for
   a non-passive IC will look up `TSCIRCUIT_FOOTPRINT_MAP` and find
   `"R_0402_1005Metric"`, which is a resistor footprint. The function should require
   `component_type` to be a known passive before applying the passive-prefix path.
