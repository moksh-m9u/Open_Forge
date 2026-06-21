# src/schemas/intent.py — Full Consumer Map and ImprovedIntentDict Impact

## Classes in src/schemas/intent.py

`FrequencySpec`, `AmbiguityFlag`, `DesignMethodology`, `IntentDict`, `BOMEntry`, `ValidatedBOM`

---

## All Source Files That Import from src.schemas.intent

### 1. `src/knowledge_graph/query/__init__.py`

**Imports:** `DesignMethodology`, `FrequencySpec`, `IntentDict`

**Fields read from IntentDict:**

| Field | Usage |
|---|---|
| `intent.goal` | `goal_mapper.map_goal_to_nodes(intent.goal, graph)` |
| `intent.design_methodology` | `.value` → `methodology_str` string |
| `intent.frequency` | None-checked; if set, `_apply_frequency_filter(intent.frequency, ...)` |

**Constructs IntentDict?** No — receives as parameter.

**Breaks if IntentDict → ImprovedIntentDict?**
- Import line breaks if class renamed and old name removed.
- Runtime safe if `ImprovedIntentDict` has `goal`, `design_methodology`, `frequency` with same types.
- `DesignMethodology` enum is imported directly — if the enum is replaced, the `.value` access on `intent.design_methodology` still works as long as it returns a string.

---

### 2. `src/schematic/__init__.py`

**Imports:** `ValidatedBOM`

**Fields read from ValidatedBOM:**

| Field | Usage |
|---|---|
| `bom.design_id` | Error `ReviewFlag.item_ref` in except block |

**Constructs ValidatedBOM?** No — receives as parameter.

**Breaks if IntentDict → ImprovedIntentDict?** No direct IntentDict access here. Safe as long as `bom.design_id` exists.

---

### 3. `src/schematic/passive_assigner.py`

**Imports:** `ValidatedBOM`

**Fields read from ValidatedBOM / BOMEntry:**

| Field | Usage |
|---|---|
| `bom.components` | Iterated to match BOM entries to datasheets |
| `entry.ref` | Matched against ref_map |
| `entry.component_type` | `.lower()` → keyword matching for capacitor/inductor/resistor |
| `entry.justification` | `re.search(...)` to extract associated ref for bypass cap naming |

**Constructs ValidatedBOM / BOMEntry?** No.

**Breaks if IntentDict → ImprovedIntentDict?** No IntentDict access. Safe.

---

### 4. `src/schematic/_ref_mapper.py`

**Imports:** `ValidatedBOM`

**Fields read from ValidatedBOM / BOMEntry:**

| Field | Usage |
|---|---|
| `bom.components` | Iterated |
| `entry.specific_part` | None-check → key in ref_map |
| `entry.ref` | Used as fallback key and value in ref_map |

**Constructs ValidatedBOM / BOMEntry?** No.

**Breaks if IntentDict → ImprovedIntentDict?** No IntentDict access. Safe.

---

### 5. `src/schematic/block_classifier.py`

**Imports:** `ValidatedBOM`

**Fields read from ValidatedBOM / BOMEntry:**

| Field | Usage |
|---|---|
| `bom.components` | Two iterations — build `ref_to_type` and `ref_blocks` |
| `entry.ref` | Dict key |
| `entry.component_type` | Passed to `_classify_component()` |

**Constructs ValidatedBOM / BOMEntry?** No.

**Breaks if IntentDict → ImprovedIntentDict?** No IntentDict access. Safe.

---

### 6. `src/bom/confidence_scorer.py`

**Imports:** `BOMEntry` (TYPE_CHECKING only)

**Fields read from BOMEntry:**

| Field | Usage |
|---|---|
| `entry.component_type` | Weight lookup via `_get_component_weight()` |
| `entry.confidence` | Multiplied by weight |

**Constructs BOMEntry?** No.

**Breaks if IntentDict → ImprovedIntentDict?** No IntentDict access. Safe.

---

### 7. `src/bom/validator.py`

**Imports:** `BOMEntry`, `ValidatedBOM` (TYPE_CHECKING only)

**Fields read from ValidatedBOM:**

| Field | Usage |
|---|---|
| `bom.components` | All three validation passes |
| `bom.review_flags` | Extended with new flags in `model_copy` |
| `bom.review_required` | ORed with `has_critical` in `model_copy` |

**Fields read from BOMEntry:**

| Field | Usage |
|---|---|
| `entry.component_type` | Power/IC type checking |
| `entry.value_constraints` | `.get("output_voltage")`, `.get("logic_voltage")` |
| `entry.ref` | In flag message strings |
| `entry.specific_part` | None-check for supplier availability |
| `entry.review_flag` | Set via `model_copy(update={"review_flag": True})` |

**Constructs ValidatedBOM?** Yes — `bom.model_copy(update={...})`. This is Pydantic's in-place copy, not a full constructor call. Does not re-validate `intent` field. **Safe even if intent type changes.**

**Breaks if IntentDict → ImprovedIntentDict?** No direct IntentDict field access. Safe at runtime; type annotations would flag it statically if `ImprovedIntentDict` is not a subtype.

---

### 8. `src/bom/generator.py`

**Imports:** `IntentDict`, `ValidatedBOM` (TYPE_CHECKING + runtime)

**Fields read from IntentDict:** None directly — passes `intent` through to `ValidatedBOM` constructor.

**Constructs ValidatedBOM?** ⚠️ **Yes — three times:**

```python
# Empty subgraph path:
return ValidatedBOM(design_id=..., intent=intent, components=[], ...)

# Normal path:
return ValidatedBOM(design_id=..., intent=intent, components=entries, ...)

# Exception path:
return ValidatedBOM(design_id=..., intent=intent, components=[], ...)
```

`ValidatedBOM.intent` is typed `IntentDict`. Pydantic v2 validates this field.
**If `ImprovedIntentDict` is not a subclass of `IntentDict`, all three ValidatedBOM
constructions raise `ValidationError` at runtime.**

---

### 9. `src/bom/selector.py`

**Imports:** `BOMEntry`, `IntentDict` (TYPE_CHECKING only)

**Fields read from IntentDict:**

| Field | Usage |
|---|---|
| `intent.goal` | Passed to `generate_justification(comp_type_node, specific_part, intent)` |

**Constructs BOMEntry?** ⚠️ **Yes:**
```python
return BOMEntry(ref=ref, component_type=..., specific_part=..., ...)
```
Constructing `BOMEntry` directly. If `BOMEntry` is renamed or its required fields change, this breaks.

**Breaks if IntentDict → ImprovedIntentDict?** Import annotation changes only — safe at runtime since it's `TYPE_CHECKING`. But `intent.goal` access breaks if the field is renamed.

---

### 10. `src/bom/justification.py`

**Imports:** `IntentDict` (TYPE_CHECKING only)

**Fields read from IntentDict:**

| Field | Usage |
|---|---|
| `intent.goal` | `intent.goal.replace("_", " ")` — used in justification template |

**Constructs IntentDict?** No.

**Breaks if IntentDict → ImprovedIntentDict?** Only if `goal` field is renamed. Import is TYPE_CHECKING only — no runtime import.

---

### 11. `src/intent/parser.py`

**Imports:** `AmbiguityFlag`, `DesignMethodology`, `FrequencySpec`, `IntentDict`

**Fields read from IntentDict:**

| Field | Usage |
|---|---|
| `intent.clarification_required` | Checked in `format_clarification_questions` |
| `intent.ambiguities` | Iterated in `format_clarification_questions` |

**Constructs IntentDict?** ⚠️ **Yes — twice:**

```python
# Draft intent (line ~387):
draft_intent = IntentDict(
    goal=..., frequency=..., application=...,
    explicit_constraints=..., inferred_constraints=...,
    design_methodology=..., board_type=...,
    ambiguities=..., clarification_required=...,
    raw_prompt=prompt,
)

# Final intent (line ~416):
return IntentDict(
    goal=..., frequency=..., application=...,
    explicit_constraints=..., inferred_constraints=...,
    design_methodology=..., board_type=...,
    ambiguities=..., clarification_required=...,
    raw_prompt=...,
)
```

**Both constructions use every field of IntentDict.**
Renaming to `ImprovedIntentDict` without updating these two sites causes `NameError` at runtime.
Changing any field names requires updates here.

---

### 12. `src/intent/ambiguity_detector.py`

**Imports:** `AmbiguityFlag`, `DesignMethodology`, `FrequencySpec`, `IntentDict`

**Fields read from IntentDict:**

| Field | Usage |
|---|---|
| `intent.goal` | RF frequency flag check |
| `intent.application` | Blank-application flag |
| `intent.design_methodology` | Compared to `DesignMethodology.RF_HIGHFREQ` |
| `intent.frequency` | None-check for RF methodology warning |
| `intent.ambiguities` | Extracts existing descriptions to avoid duplicates |

**Constructs AmbiguityFlag?** Yes — several, but `AmbiguityFlag` is a data model, not `IntentDict`.

**Breaks if IntentDict → ImprovedIntentDict?** Import name must change. Five field accesses must survive renaming.

---

### 13. `src/intent/methodology_classifier.py`

**Imports:** `DesignMethodology`

**Fields read:** None from IntentDict — only uses `DesignMethodology` enum values.

**Constructs DesignMethodology?** Uses `DesignMethodology(meth_name)` enum instantiation.

**Breaks if IntentDict → ImprovedIntentDict?** Not affected — no IntentDict usage.

---

### 14. `src/intent/pipeline.py`

**Imports:** `DesignMethodology`, `IntentDict`, `ValidatedBOM`

**Fields read from IntentDict:**

| Field | Usage |
|---|---|
| `intent.clarification_required` | Gates whether to query the KG |

**Constructs IntentDict?** ⚠️ **Yes — in the exception fallback:**

```python
fallback_intent = IntentDict(
    goal="unknown",
    application="unknown",
    design_methodology=DesignMethodology.STANDARD_SMD,
    board_type="standard_SMD",
    raw_prompt=prompt,
    clarification_required=True,
)
```

**Constructs ValidatedBOM?** Yes — via `_empty_bom(intent)` which calls:
```python
ValidatedBOM(design_id=..., intent=intent, components=[], ...)
```

Both construction sites break if `IntentDict` is renamed without updating this file.

---

### 15. `src/synthesis/pipeline.py`

**Imports:** `ValidatedBOM`

**Fields read from ValidatedBOM:**

| Field | Usage |
|---|---|
| `bom.design_id` | `_failure_nir(bom, reason)` |
| `bom.intent.raw_prompt` | NIR `prompt` field |
| `bom.intent.design_methodology.value` | NIR `design_methodology` field |

**Constructs ValidatedBOM?** No — receives as parameter.

**Breaks if IntentDict → ImprovedIntentDict?** Only if `raw_prompt` or `design_methodology` are renamed on the new class.

---

### 16. `src/review/queue.py`

**Imports:** `ValidatedBOM`

**Fields read from ValidatedBOM:**

| Field | Usage |
|---|---|
| `bom.review_flags` | Severity check; passed as `flags` to `_write_item` |
| `bom.design_id` | `component_id` in queue item |

**Constructs ValidatedBOM?** No.

**Breaks if IntentDict → ImprovedIntentDict?** No IntentDict field access. Safe.

---

### 17. `src/nir/builder.py`

**Imports:** `ValidatedBOM`

**Fields read from ValidatedBOM:**

| Field | Usage |
|---|---|
| `bom.components` | Iterated to build `ComponentRef` list |
| `bom.design_id` | NIR `design_id` |
| `bom.intent.raw_prompt` | NIR `prompt` |
| `bom.intent.design_methodology.value` | NIR `design_methodology` |
| `bom.review_flags` | Converted to `ReviewFlag` objects |

**Fields read from BOMEntry:**

| Field | Usage |
|---|---|
| `entry.ref` | ComponentRef and dict keys |
| `entry.specific_part` | ComponentRef `component_id`, datasheet lookup |
| `entry.component_type` | ComponentRef |
| `entry.value_constraints` | `.get("value")` for passive value |
| `entry.confidence` | `confidence_scores` dict value |
| `entry.justification` | `justifications` dict value |
| `entry.source` | `source_citations` dict value |

**Constructs ValidatedBOM?** No.

**Breaks if IntentDict → ImprovedIntentDict?** Only if `raw_prompt` or `design_methodology` are renamed.

---

## Impact Summary: Replacing IntentDict with ImprovedIntentDict

### Critical Breaks (runtime errors)

| File | Break type | Reason |
|---|---|---|
| `bom/generator.py` | `ValidationError` | Constructs `ValidatedBOM(intent=intent, ...)` — Pydantic validates `intent: IntentDict` field. If `ImprovedIntentDict` is not a subclass, validation fails on all 3 construction sites. |
| `intent/parser.py` | `NameError` | Constructs `IntentDict(...)` twice — hardcodes the class name |
| `intent/pipeline.py` | `NameError` | Constructs `IntentDict(...)` once in exception fallback |

### Import-level Breaks (if old name removed)

All files with `from src.schemas.intent import IntentDict` would raise `ImportError` on load:
`knowledge_graph/query/__init__.py`, `bom/selector.py`, `bom/justification.py`,
`bom/generator.py`, `intent/parser.py`, `intent/ambiguity_detector.py`, `intent/pipeline.py`

### Field-access Breaks (if field renamed on ImprovedIntentDict)

| Field renamed | Files broken |
|---|---|
| `goal` | `bom/justification.py`, `knowledge_graph/query/__init__.py`, `intent/ambiguity_detector.py` |
| `application` | `intent/ambiguity_detector.py` |
| `design_methodology` | `knowledge_graph/query/__init__.py`, `synthesis/pipeline.py`, `nir/builder.py`, `intent/pipeline.py`, `intent/ambiguity_detector.py` |
| `frequency` | `knowledge_graph/query/__init__.py`, `intent/ambiguity_detector.py` |
| `clarification_required` | `intent/pipeline.py`, `intent/ambiguity_detector.py` |
| `ambiguities` | `intent/parser.py`, `intent/ambiguity_detector.py` |
| `raw_prompt` | `synthesis/pipeline.py`, `nir/builder.py`, `intent/pipeline.py` |

### Safe Files (no IntentDict field access, or TYPE_CHECKING only)

`schematic/__init__.py`, `schematic/passive_assigner.py`, `schematic/_ref_mapper.py`,
`schematic/block_classifier.py`, `bom/confidence_scorer.py`, `bom/validator.py`,
`review/queue.py`, `intent/methodology_classifier.py`

---

## Safest Migration Path

If `IntentDict` must be replaced:

1. Make `ImprovedIntentDict` a **subclass of `IntentDict`** — Pydantic v2 accepts subclass instances for a parent-typed field, which fixes the `bom/generator.py` ValidationError.
2. Add `IntentDict = ImprovedIntentDict` alias in `src/schemas/intent.py` — fixes all import sites without touching them.
3. Update the three direct construction sites (`parser.py` ×2, `pipeline.py` ×1) to use the new class name.
4. Only then remove the alias once all callers are updated.
