# Field Trace: ComponentDatasheet.layout_constraints

## Definition

**File:** `src/schemas/datasheet.py` line 333
```python
layout_constraints: list[PlacementConstraint] = Field(
    default_factory=list,
    description="Phase 5: layout recommendation constraints",
)
```
Default is `[]`. Phase 1–4 extraction leaves it empty. Phase 5 (layout section NLP)
populates it. An empty list is a valid and common state.

---

## Step 1: Phase 5 Output → p1_importer.py

**File:** `src/knowledge_graph/importers/p1_importer.py`

### `_create_placement_rule_nodes` (lines 195–244)
```python
constraints = datasheet.layout_constraints or []
for i, constraint in enumerate(constraints):
    ...
    nodes.append(node)
return nodes
```

**Empty list:** `datasheet.layout_constraints or []` evaluates to `[]`.
The loop body never executes. Returns `[]`.
`result.placement_rules_imported` is set to `len([])` = 0.

**Handles empty?** ✅ Yes — `or []` defensive guard plus zero-iteration loop is safe.
(Note: `or []` is redundant since the schema default is already `[]`, but harmless.)

### `_create_component_to_rule_edges` (lines 316–344)
```python
constraints = datasheet.layout_constraints or []
for i, constraint in enumerate(constraints):
    ...
return edges
```

**Empty list:** Same pattern — loop doesn't run, returns `[]`.

**Handles empty?** ✅ Yes.

### `import_datasheet` integration (lines 416–434)
```python
rule_nodes = _create_placement_rule_nodes(datasheet, now)
...
result.placement_rules_imported = len(rule_nodes)

rule_edges = _create_component_to_rule_edges(datasheet)
edges_to_add.extend(rule_edges)
```

**Empty list:** `rule_nodes = []`, `rule_edges = []`. Both `extend` and `len` of
empty lists are safe. Zero nodes and zero edges are added to the graph.

**Handles empty?** ✅ Yes.

---

## Step 2: Knowledge Graph → Query Engine

**File:** `src/knowledge_graph/query/__init__.py` (`query_graph`)
and `src/knowledge_graph/query/result_builder.py` (`build_subgraph`)

### What flows from layout_constraints into the KG

If `layout_constraints` was empty in Step 1, **no `PLACEMENT_RULE` nodes were
written to the KG** for that component. The BFS traversal in `traversal.bfs_traverse`
will simply never encounter any `PLACEMENT_RULE` nodes for that component.

### `build_subgraph` (result_builder.py lines 48–93)
```python
raw_placement_rules: list[KGNode] = []
...
for node_id in path_confidences:
    node = graph.get_node(node_id)
    ...
    elif node.node_type == KGNodeType.PLACEMENT_RULE:
        raw_placement_rules.append(node)
```

**Empty list upstream:** `raw_placement_rules` stays `[]` if no `PLACEMENT_RULE`
nodes were in the traversal.

### `apply_methodology_filter` (methodology_filter.py lines 40–60)
```python
def apply_methodology_filter(
    placement_rule_nodes: list[KGNode],
    methodology_node: Optional[KGNode],
) -> list[KGNode]:
    if methodology_node is None:
        return placement_rule_nodes   # returns []
    ...
    if not active_types:
        return placement_rule_nodes   # returns []
    kept: list[KGNode] = []
    for node in placement_rule_nodes:  # loop doesn't run
        ...
    return kept  # returns []
```

**Empty list:** All three early-return/loop paths return `[]` safely.

**Handles empty?** ✅ Yes — every code path in this function is safe with `[]`.

### `DesignSubgraph.placement_rules` (kg.py line 218)
```python
placement_rules: list[KGNode] = Field(default_factory=list, ...)
```

**Empty list:** `placement_rules=[]` is written into the `DesignSubgraph`.
`DesignSubgraph` has `model_config = {"extra": "forbid"}` but `[]` is a valid
value for a `list[KGNode]` field.

**Handles empty?** ✅ Yes.

---

## Step 3: DesignSubgraph → constraint_collector.py → NIR

**File:** `src/layout/constraint_collector.py` (`collect_constraints`)

```python
def collect_constraints(
    schematic: SchematicGraph,
    datasheets: list[ComponentDatasheet],
    subgraph: DesignSubgraph,
) -> list[NIRConstraint]:

    phase5_constraints: list[NIRConstraint] = []
    phase5_keys: set[tuple[str, str]] = set()

    for datasheet in datasheets:
        source = f"phase5:{datasheet.component_id}"
        for ds_constraint in datasheet.layout_constraints:   # inner loop
            nir_constraint = _ds_to_nir(ds_constraint, source)
            phase5_constraints.append(nir_constraint)
            phase5_keys.add(_constraint_key(nir_constraint))

    merged: list[NIRConstraint] = list(phase5_constraints)

    for rule_node in subgraph.placement_rules:               # outer loop
        kg_constraint = _kg_node_to_nir(rule_node)
        key = _constraint_key(kg_constraint)
        if key in phase5_keys:
            continue
        merged.append(kg_constraint)

    return merged
```

**Both sources empty:**
- Inner loop over `datasheet.layout_constraints` = `[]` → never runs.
- `phase5_constraints = []`, `phase5_keys = set()`.
- Outer loop over `subgraph.placement_rules` = `[]` → never runs.
- `merged = []`.
- Returns `[]`.

**Handles empty?** ✅ Yes — no assumption of at least one entry anywhere.

**Priority logic with empty Phase 5:** If `datasheet.layout_constraints` is empty
but `subgraph.placement_rules` is non-empty (KG-4 has rules), those KG rules flow
through unchecked since `phase5_keys` is empty. This is correct behaviour by design
— Phase 5 constraints take priority over KG-4 only when they exist.

---

## Step 4: NIR.placement_constraints → tscircuit_serializer.py → TSX

**File:** `src/output/tscircuit_serializer.py` (`_generate_tsx`, lines 134–141)

```python
lines.append("// ── Placement Constraints ───────────────────────────")
for constraint in nir.placement_constraints:
    if constraint.max_distance_mm is not None:
        lines.append(
            f'circuit.place("{constraint.ref}", '
            f'{{ near: "{constraint.relative_to}", '
            f'maxDistance: "{constraint.max_distance_mm}mm" }})'
        )
```

**Empty list:** The section header comment is always written. The loop body
never executes. No `circuit.place(...)` calls are emitted.

**Handles empty?** ✅ Yes — zero-iteration loop is safe. The comment line is
harmless (it becomes a TSX comment).

**Partial handling note:** Even for non-empty lists, only constraints with
`max_distance_mm is not None` produce output. Constraints of type `keepout`,
`layer`, `orientation`, or `group` — and proximity constraints without a
distance value — are silently skipped. This is a separate gap unrelated to
the empty-list case but worth noting for completeness.

---

## Full Chain Summary

| Step | File | Empty list behaviour | Safe? |
|---|---|---|---|
| Phase 5 → importer | `p1_importer.py` `_create_placement_rule_nodes` | Returns `[]` | ✅ |
| Phase 5 → importer | `p1_importer.py` `_create_component_to_rule_edges` | Returns `[]` | ✅ |
| KG traversal | `result_builder.py` `build_subgraph` | `raw_placement_rules = []` | ✅ |
| Methodology filter | `methodology_filter.py` `apply_methodology_filter` | Returns `[]` on all paths | ✅ |
| DesignSubgraph field | `kg.py` `DesignSubgraph.placement_rules` | `[]` is valid schema value | ✅ |
| Constraint collection | `constraint_collector.py` `collect_constraints` | Returns `[]` | ✅ |
| NIR field | `nir.py` `NIR.placement_constraints` | `[]` is valid schema value | ✅ |
| TSX generation | `tscircuit_serializer.py` `_generate_tsx` | Loop skipped, header written | ✅ |

**Every step handles an empty list correctly. There are no crashes, no
assumptions of at least one entry, and no silent wrong outputs specific to
the empty case.**

---

## Ancillary Gap (Non-Empty Case)

In `tscircuit_serializer.py`, only `proximity` constraints with `max_distance_mm`
set produce TSX output. The following constraint types are silently dropped even
when the list is non-empty:

- `keepout` — no `circuit.place()` equivalent emitted
- `layer` — no layer assignment emitted
- `orientation` — no rotation hint emitted
- `group` — no grouping directive emitted
- Proximity constraints where `max_distance_mm is None`

This is not an empty-list issue but means the TSX output is an incomplete
representation of the NIR's placement constraints.
