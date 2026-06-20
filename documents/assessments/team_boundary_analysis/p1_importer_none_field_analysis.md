# p1_importer.py — None Field Analysis

## Fields Read from ComponentDatasheet

| Field | Type in schema | Optional? |
|---|---|---|
| `component_id` | `str` | No |
| `manufacturer` | `str` | No |
| `description` | `str` | No |
| `package` | `str` | No |
| `source_pdf_hash` | `str` | No |
| `extraction_confidence` | `float` | No |
| `extraction_method` | `ExtractionMethod` | No |
| `review_flags` | `list[str]` | No (default `[]`) |
| `pins` | `list[PinDefinition]` | No (default `[]`) |
| `electrical_parameters` | `list[ElectricalParameter]` | No (default `[]`) |
| `layout_constraints` | `list[PlacementConstraint]` | No (default `[]`) |

### Sub-fields from PinDefinition

| Field | Optional? |
|---|---|
| `pin_number` | No |
| `raw_name` | No |
| `normalized_function` | **Yes** (`Optional[str] = None`) |
| `pin_type` | **Yes** (`Optional[str] = None`) |
| `description` | **Yes** (`Optional[str] = None`) |
| `alternate_functions` | No (default `[]`) |

### Sub-fields from ElectricalParameter / ExtractedValue

| Field | Optional? |
|---|---|
| `parameter_name` | No |
| `symbol` | **Yes** (`Optional[str] = None`) |
| `conditions` | **Yes** (`Optional[str] = None`) |
| `section_type` | No |
| `value` (ExtractedValue) | No |
| `value.confidence` | No |
| `value.min_val` | **Yes** |
| `value.typ_val` | **Yes** |
| `value.max_val` | **Yes** |
| `value.unit` | **Yes** |

### Sub-fields from PlacementConstraint (datasheet schema)

| Field | Optional? |
|---|---|
| `constraint_type` | No |
| `subject` | No |
| `relative_to` | No |
| `relative_to_type` | No |
| `hard` | No |
| `confidence` | No |
| `source_sentence` | No |
| `max_distance_mm` | **Yes** |
| `min_distance_mm` | **Yes** |
| `layer` | **Yes** |

---

## Unhandled None Cases

Three Optional fields are written directly into `KGNode.properties` dicts without a None guard. None of these crash `p1_importer` (Python dicts accept `None`), but they store `None` inconsistently — downstream KG consumers reading these keys may receive `None` when they expect a string.

### 1. `param.symbol` stored raw (`_create_electrical_property_nodes`, line 157)

```python
# Line 150: node ID correctly uses fallback
symbol = param.symbol or "unknown"

# Line 157: but the stored property is the raw (possibly None) value
properties = {
    "symbol": param.symbol,   # <-- can be None
    ...
}
```

**Contrast:** `pin.normalized_function` is guarded before storing:
```python
if pin.normalized_function is not None:
    properties["normalized_function"] = pin.normalized_function
```

### 2. `param.conditions` stored raw (`_create_electrical_property_nodes`, line 158)

```python
properties = {
    ...
    "conditions": param.conditions,  # <-- Optional[str], no guard
}
```

**Contrast:** `pin.description` is guarded:
```python
if pin.description:
    properties["description"] = pin.description
```

### 3. `pin.pin_type` stored raw (`_create_pin_nodes`, line 107)

```python
properties = {
    ...
    "pin_type": pin.pin_type,  # <-- Optional[str], no guard
    ...
}
```

---

## Risk Assessment

| Case | Crash in p1_importer? | Risk to downstream |
|---|---|---|
| `param.symbol = None` in properties | No | Medium — KG queries filtering on `symbol` may fail or return wrong results |
| `param.conditions = None` in properties | No | Low — conditions is informational |
| `pin.pin_type = None` in properties | No | Medium — routing/placement logic that branches on `pin_type` may hit None unexpectedly |

## Recommendation

Add None guards consistent with the existing pattern for `normalized_function` and `description`:

```python
# In _create_electrical_property_nodes
if param.symbol is not None:
    properties["symbol"] = param.symbol
if param.conditions is not None:
    properties["conditions"] = param.conditions

# In _create_pin_nodes
if pin.pin_type is not None:
    properties["pin_type"] = pin.pin_type
```
