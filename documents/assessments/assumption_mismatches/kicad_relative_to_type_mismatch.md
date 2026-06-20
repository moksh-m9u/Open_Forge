# Assumption Mismatch: NIR.PlacementConstraint.relative_to_type vs kicad_serializer.py

## Schema Contract

**File:** `src/schemas/nir.py` lines 161–163
```python
relative_to_type: Literal[
    "component", "pin", "board_edge"
] = Field(description="Type of the relative_to target: component, pin, or board_edge — BS-2 fix")
```

The schema defines three semantically distinct values:
- `"component"` — constraint is measured against another component's body
- `"pin"` — constraint is measured against a specific pin
- `"board_edge"` — constraint is measured against the PCB boundary

The BS-2 fix comment signals this field was added deliberately to carry
placement semantics downstream.

---

## What kicad_serializer.py Actually Does

**File:** `src/output/kicad_serializer.py` lines 216–226

```python
keepouts = [
    c for c in nir.placement_constraints if c.constraint_type == "keepout"
]
for keepout in keepouts:
    client.call(
        "add_keepout_zone",
        {
            "reference": keepout.ref,
            "clearance_mm": keepout.min_distance_mm or 1.0,
        },
    )
```

**`relative_to_type` is never read.**

The serializer:
1. Filters constraints to `constraint_type == "keepout"` only.
2. Passes `ref` and `min_distance_mm` to the MCP tool.
3. Discards every other field: `relative_to`, `relative_to_type`, `layer`,
   `hard`, `confidence`, `source`.

---

## Branching Behaviour

| `relative_to_type` value | Code path taken | Correct KiCad output? |
|---|---|---|
| `"component"` | `add_keepout_zone` with ref + clearance_mm | Partial — no anchor component specified |
| `"pin"` | `add_keepout_zone` with ref + clearance_mm | Wrong — pin-relative keepout needs pin reference |
| `"board_edge"` | `add_keepout_zone` with ref + clearance_mm | Wrong — board-edge keepout needs edge geometry, not component ref |

All three values produce **identical behaviour**. There is no branching.
No unhandled-value error is possible because the field is never read.

---

## What Happens with Each Value

### `"component"` (closest to correct)
A component-relative keepout zone is the closest semantic match for
`add_keepout_zone { reference, clearance_mm }`. The output is still incomplete
because `relative_to` (which component to keep away from) is not passed —
KiCad receives only the subject component's ref and a clearance distance,
not the anchor.

### `"pin"` (wrong)
A pin-relative keepout should reference a specific pin, not just a component.
The MCP call uses `ref` (the subject component) and `clearance_mm` only.
The pin identity (`relative_to` + `pin_number`) is dropped. KiCad will place
a component-level keepout rather than a pin-level one.

### `"board_edge"` (wrong)
A board-edge keepout is a courtyard/edge-clearance rule, not a component
proximity rule. The correct KiCad representation would be an edge-clearance
constraint or board outline zone rule, not `add_keepout_zone` parameterised
by a component reference. The generated KiCad data is semantically incorrect.

---

## Compounding Gap: Non-Keepout Constraints Dropped Entirely

The serializer only processes `constraint_type == "keepout"`. The other four
NIR constraint types are silently ignored regardless of `relative_to_type`:

| `constraint_type` | Serialized? |
|---|---|
| `keepout` | ✅ Yes (partially — see above) |
| `proximity` | ❌ No |
| `layer` | ❌ No |
| `orientation` | ❌ No |
| `group` | ❌ No |

---

## Root Cause

The KiCad MCP tool `add_keepout_zone` has a single call signature
`{ reference, clearance_mm }`. The serializer was written against this
simplified interface and never extended to handle the full NIR constraint
vocabulary. `relative_to_type` was added to the NIR schema (BS-2 fix) to
preserve placement semantics, but no corresponding branching was added in
the serializer to act on those semantics.

---

## Risk Assessment

| Scenario | Impact |
|---|---|
| `relative_to_type = "component"` keepout | Partial — anchor component lost, clearance applied as absolute zone |
| `relative_to_type = "pin"` keepout | Wrong geometry — pin-level constraint treated as component-level |
| `relative_to_type = "board_edge"` keepout | Wrong type — edge clearance emitted as component keepout zone |
| Any proximity/layer/orientation/group constraint | Silently dropped from KiCad output |

None of these cause a runtime error. All failures are silent and produce
a KiCad file that does not faithfully represent the NIR's design intent.

---

## Recommendation

The serializer needs a branching strategy per `relative_to_type` for keepout
constraints, and support for the other constraint types:

```python
for constraint in nir.placement_constraints:
    if constraint.constraint_type == "keepout":
        if constraint.relative_to_type == "board_edge":
            client.call("set_edge_clearance", {
                "reference": constraint.ref,
                "clearance_mm": constraint.min_distance_mm or 1.0,
            })
        else:  # "component" or "pin"
            client.call("add_keepout_zone", {
                "reference": constraint.ref,
                "relative_to": constraint.relative_to,
                "clearance_mm": constraint.min_distance_mm or 1.0,
            })
    elif constraint.constraint_type == "proximity":
        client.call("add_proximity_rule", {
            "reference": constraint.ref,
            "near": constraint.relative_to,
            "max_distance_mm": constraint.max_distance_mm,
        })
    # layer, orientation, group similarly
```
