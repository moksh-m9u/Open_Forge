# Config Field Access Analysis

## All Config Fields and Their Defaults

Every field in `src/config.py` has a default value. There are **no required fields**.
Missing keys in `default.yaml` fall back to the code-level default without raising.

| Field | Code Default | In default.yaml? |
|---|---|---|
| `model_paths` | `{"qwen25_7b": ..., "qwen2_vl_7b": ..., "yolov8n_doclaynet": ..., "locateanything_3b": ...}` | Yes (all 4 keys) |
| `corpus_dir` | `Path("corpus")` | Yes |
| `output_dir` | `Path("output")` | Yes |
| `confidence_thresholds` | `{"bom_total": 0.95, "bom_component": 0.90, "pin_normalization": 0.85}` | Yes (different values — see Gap 1) |
| `review_queue_path` | `Path("output/review_queue.json")` | Yes |
| `neo4j_uri` | `"bolt://localhost:7687"` | Yes |
| `graph_path` | `Path("output/knowledge_graph.graphml")` | Yes |
| `supplier_cache_path` | `Path("data/supplier_cache.db")` | **No** |
| `canonical_functions_path` | `Path("configs/canonical_functions.yaml")` | **No** |
| `kg_traversal_max_depth` | `4` | Yes |
| `kg_min_edge_confidence` | `0.60` | Yes |
| `log_level` | `"INFO"` | Yes |
| `kicad_mcp_url` | `"http://localhost:3000")` | **No** |

---

## Module-by-Module Config Access Audit

### 1. `src/bom/generator.py`

```python
bom_total_threshold = getattr(config, "confidence_thresholds", {}).get("bom_total", 0.85)
bom_component_threshold = getattr(config, "confidence_thresholds", {}).get("bom_component", 0.75)
```

**Access pattern:** `getattr` with empty-dict fallback, then `.get()` with numeric fallback.
**Handles missing field?** ✅ Yes — double-guarded.
**Gap:** See Gap 1 below — the `.get()` fallbacks (0.85, 0.75) match the YAML values, not the
code-default values (0.95, 0.90). If the YAML key disappears, the module silently uses the
`.get()` fallback rather than the Pydantic code default.

---

### 2. `src/knowledge_graph/ingestion/triple_extractor.py`

```python
DEFAULT_TRIPLE_MIN_CONFIDENCE = 0.65

thresholds = getattr(config, "confidence_thresholds", {})
value = thresholds.get("triple_min", DEFAULT_TRIPLE_MIN_CONFIDENCE)
```

**Docstring (line 62) says:** `config.confidence_thresholds["triple_min"]` — direct subscript,
which would raise `KeyError` if missing. But the actual code uses `.get()`. **Docstring is wrong.**

**Access pattern:** `getattr` + `.get()` with module-level fallback.
**Handles missing field?** ✅ Yes — safe at runtime.
**Gap:** `"triple_min"` is present in default.yaml but **absent from the code-default dict**:
```python
# Code default in config.py:
{"bom_total": 0.95, "bom_component": 0.90, "pin_normalization": 0.85}
# No "triple_min" key
```
If default.yaml is used (normal), `triple_min = 0.65` from YAML.
If default.yaml is absent (bare Pydantic default), `triple_min` is missing from the dict and the
module falls back to `DEFAULT_TRIPLE_MIN_CONFIDENCE = 0.65` — same value, coincidentally consistent.

---

### 3. `src/knowledge_graph/query/__init__.py`

```python
max_depth = config.kg_traversal_max_depth
min_confidence = config.kg_min_edge_confidence
```

**Access pattern:** Direct attribute access. No guard.
**Handles missing field?** ✅ Yes — both fields have code defaults (`4` and `0.60`).
If absent from YAML, Pydantic falls back to defaults at construction time.
No runtime error possible.

---

### 4. `src/output/kicad_serializer.py`

```python
client = mcp_client or KiCadMCPClient(config.kicad_mcp_url)
```

**Access pattern:** Direct attribute access.
**Handles missing field?** ✅ Yes — `kicad_mcp_url` has code default `"http://localhost:3000"`.
`kicad_mcp_url` is **absent from default.yaml** but the code default applies.

---

### 5. `src/knowledge_graph/admin/cli.py`

```python
graph_path = config.graph_path
```

**Access pattern:** Direct attribute access (four call sites).
**Handles missing field?** ✅ Yes — `graph_path` has code default.

---

### 6. `src/review/queue.py`

```python
if hasattr(config, "review_queue_path") and config.review_queue_path:
    return config.review_queue_path
if hasattr(config, "output_dir") and config.output_dir:
    return Path(config.output_dir) / "review_queue.db"
```

**Access pattern:** `hasattr` guard before every access.
**Handles missing field?** ✅ Yes — most defensive pattern in the codebase.

---

### 7. `src/schematic/net_assigner.py`

```python
# Line 61 — MODULE LEVEL (executed at import time):
PROTOCOL_GROUPS: dict[str, _ProtocolGroup] = load_protocol_groups(get_config())

# Inside load_protocol_groups:
path = Path(config.canonical_functions_path)
if not path.exists():
    raise FileNotFoundError(f"Canonical functions file not found: {path}")
```

**Access pattern:** Direct attribute access.
**Handles missing field?** ✅ Field has code default `Path("configs/canonical_functions.yaml")`.

**Critical behaviour:** `load_protocol_groups(get_config())` is called at **module import time**,
not at call time. If `canonical_functions_path` points to a non-existent file, `FileNotFoundError`
is raised the moment `net_assigner` is imported — before any function in it can be called.
This turns a runtime error into an **import-time crash** that surfaces earlier but with a less
informative traceback for callers who don't expect import failures.

---

### 8. `src/knowledge_graph/pin_normalizer/dictionary.py`

```python
path = Path(config.canonical_functions_path)
```

**Access pattern:** Direct attribute access.
**Handles missing field?** ✅ Field has code default.

---

### 9. `src/datasheet/phase1_dla/detector.py`

```python
model_path = config.get_model_path("yolov8n_doclaynet")
```

**`get_model_path` implementation:**
```python
def get_model_path(self, model_name: str) -> Path:
    if model_name not in self.model_paths:
        raise KeyError(f"Model '{model_name}' not found ...")
    return self.model_paths[model_name]
```

**Access pattern:** Dict key access that raises `KeyError` if missing.
**Handles missing field?** ⚠️ Conditionally safe. When `from_yaml` loads default.yaml,
`model_paths` is **replaced wholesale** by the YAML dict. If the YAML has all four keys
(it currently does), this is safe. If `yolov8n_doclaynet` is removed from default.yaml or
YAML is absent and the code default applies, safety depends on whether the code default
contains the key — it does. **But the YAML replaces the code default entirely**, so a
partial YAML `model_paths` (missing one key) would cause a `KeyError` at runtime.

---

### 10. `src/datasheet/phase2_tsr/path_b_vlm.py`

```python
model_path = config.get_model_path("qwen2_vl_7b")
```

Same risk as Reader 9. Raises `KeyError` if `qwen2_vl_7b` is absent from the loaded
`model_paths` dict.

---

### 11. `src/datasheet/phase5_layout/spatial_parser.py`

```python
model_path = Path(config.model_paths.get("qwen25_7b", ""))
```

**Access pattern:** `.get()` with empty-string fallback. Safe — no `KeyError` possible.
**Gap:** Empty-string path `Path("")` resolves to the current directory, not a model file.
If `qwen25_7b` is missing, the fallback silently produces a wrong path rather than an error.

---

## Gaps and Mismatches

### Gap 1 (CRITICAL): `confidence_thresholds` code default vs YAML values differ

| Key | Code default | default.yaml | Who wins when YAML present |
|---|---|---|---|
| `bom_total` | `0.95` | `0.85` | YAML: `0.85` |
| `bom_component` | `0.90` | `0.75` | YAML: `0.75` |
| `pin_normalization` | `0.85` | `0.70` | YAML: `0.70` |
| `triple_min` | *(absent)* | `0.65` | YAML: `0.65` |

`from_yaml` replaces the entire dict when the YAML key is present. So in production
(YAML present) thresholds are 10–15% lower than the code defaults suggest. If someone
runs without a YAML file and reads the code defaults, they would expect stricter thresholds
than the system actually applies. This is a silent discrepancy with no warning.

### Gap 2: `pcb`, `schematic`, `layout` sections in YAML are dead config

default.yaml contains:
```yaml
pcb:
  default_grid_size: 0.0254
  max_trace_width: 10.0
  min_trace_clearance: 0.1
  default_copper_weight: 35
schematic:
  default_sheet_size: "A4"
  title_block_template: "templates/title_block.json"
layout:
  default_board_thickness: 1.6
  max_layer_count: 12
  preferred_layers: 4
```

None of these have corresponding `Config` fields. `from_yaml`'s `field_mapping` dict does
not include `pcb`, `schematic`, or `layout`. These values are loaded from YAML and
**silently discarded**. No consumer can access them via `config.pcb` etc.
`Config` has `model_config = SettingsConfigDict(extra="ignore")` which suppresses the error.

### Gap 3: `supplier_cache_path` is in Config but absent from YAML and no module reads it

The field exists in `Config` with default `Path("data/supplier_cache.db")` but:
- It is not in default.yaml
- No `grep` hit shows any module reading `config.supplier_cache_path`

This field appears to be a placeholder that was never wired up.

### Gap 4: `model_paths` is replaced wholesale by YAML

`from_yaml` passes the entire YAML `model_paths` dict to Pydantic, which replaces the
code-default dict. A partial `model_paths` in the YAML (e.g., only two of four keys)
would cause `get_model_path()` to raise `KeyError` for the missing keys at runtime,
with no fallback to the code defaults for the missing entries.

### Gap 5: `net_assigner.py` fails at import time, not call time

`PROTOCOL_GROUPS = load_protocol_groups(get_config())` runs at module level.
If `canonical_functions_path` is wrong or the file is missing, the module raises
`FileNotFoundError` on import. Any caller that catches exceptions at the function-call
level will not catch this — the import itself crashes.

### Gap 6: `spatial_parser.py` silent wrong-path fallback

`config.model_paths.get("qwen25_7b", "")` returns `""` if the key is missing,
producing `Path("")` which silently resolves to the current working directory.
This is a worse failure mode than `KeyError` — the model loader will attempt to
load a model from CWD and fail with a confusing error.

---

## Summary Table

| Module | Field accessed | Safe if YAML missing? | Notes |
|---|---|---|---|
| `bom/generator.py` | `confidence_thresholds["bom_total/bom_component"]` | ✅ | Double-guarded |
| `triple_extractor.py` | `confidence_thresholds["triple_min"]` | ✅ | Module fallback constant |
| `query/__init__.py` | `kg_traversal_max_depth`, `kg_min_edge_confidence` | ✅ | Code defaults apply |
| `kicad_serializer.py` | `kicad_mcp_url` | ✅ | Code default applies |
| `admin/cli.py` | `graph_path` | ✅ | Code default applies |
| `review/queue.py` | `review_queue_path`, `output_dir` | ✅ | `hasattr` guards |
| `net_assigner.py` | `canonical_functions_path` | ✅ field / ⚠️ timing | Import-time crash if file missing |
| `pin_normalizer/dictionary.py` | `canonical_functions_path` | ✅ | Code default applies |
| `phase1_dla/detector.py` | `model_paths["yolov8n_doclaynet"]` | ✅ full YAML / ⚠️ partial | KeyError on partial YAML model_paths |
| `phase2_tsr/path_b_vlm.py` | `model_paths["qwen2_vl_7b"]` | ✅ full YAML / ⚠️ partial | KeyError on partial YAML model_paths |
| `phase5_layout/spatial_parser.py` | `model_paths.get("qwen25_7b", "")` | ⚠️ silent | Wrong path if key missing |
