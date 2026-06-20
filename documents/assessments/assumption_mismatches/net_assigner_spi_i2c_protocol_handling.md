# Assumption Mismatch: net_assigner.py SPI + I2C Protocol Handling

## Protocol Groups from canonical_functions.yaml

```yaml
protocols:
  SPI:
    shared:  [SPI_CLOCK, SPI_DATA_IN, SPI_DATA_OUT]
    unique:  [SPI_CHIP_SELECT]
  I2C:
    shared:  [I2C_DATA, I2C_CLOCK]
    unique:  []
  UART:
    crossover: [[UART_TRANSMIT, UART_RECEIVE]]
    unique:  []
```

After `load_protocol_groups` runs, `assign_protocol_nets` builds:

```python
shared_functions = {SPI_CLOCK, SPI_DATA_IN, SPI_DATA_OUT, I2C_DATA, I2C_CLOCK}
unique_functions  = {SPI_CHIP_SELECT}
```

Both sets are Python `set` objects — **iteration order is non-deterministic**.

---

## What Happens to a Component with Both SPI and I2C Pins

For a microcontroller with pins normalized to:
`SPI_CLOCK`, `SPI_DATA_IN`, `SPI_DATA_OUT`, `SPI_CHIP_SELECT`, `I2C_CLOCK`, `I2C_DATA`

### Shared loop (lines 231–243)

```python
for func in shared_functions:   # unordered set
    matches = function_pins.get(func, [])
    if not matches:
        continue
    ...
    nets.append(_build_net(base_name, net_type, connections, pins_only, ...))
    for ref, pin in matches:
        assigned.add((ref, pin.pin_number))
```

Each function is an independent key in `function_pins`. When the loop reaches
`SPI_CLOCK`, it collects only pins with `normalized_function == "SPI_CLOCK"`.
When it reaches `I2C_CLOCK`, it collects only pins with `normalized_function == "I2C_CLOCK"`.
These are disjoint sets — no pin can have two `normalized_function` values.

**I2C pins are processed regardless of whether SPI was processed first.**
Set iteration order affects which protocol loop runs first, but since there is
no `break`, no early exit, and the `assigned` set is only used in the fallback
loop (not here), order has no effect on correctness.

**Result for SPI + I2C component: all six function types produce their own net.
I2C pins are fully independent of SPI processing order. ✅**

### Unique loop (lines 245–259)

`SPI_CHIP_SELECT` (the only unique function) creates one net per component ref:
`SPI_CS_U1`, `SPI_CS_U2`, etc. This correctly models real SPI topology where
each peripheral has its own chip select line on a shared bus.

### Fallback loop (lines 284–299)

```python
for func, matches in function_pins.items():
    if func in shared_functions or func in unique_functions:
        continue   # SPI and I2C functions are all skipped here
```

All SPI and I2C functions were handled above, so this loop skips them entirely.

---

## Bugs and Gaps Found

### Bug 1: `uart_group` is a dead variable

**Lines 261–263:**
```python
uart_group = PROTOCOL_GROUPS["UART"]
tx_pins = function_pins.get("UART_TRANSMIT", [])
rx_pins = function_pins.get("UART_RECEIVE", [])
```

`uart_group` is assigned but **never referenced again**. The UART crossover
logic (`UART_TRANSMIT ↔ UART_RECEIVE`) is hardcoded directly in the function
rather than being driven by `uart_group["crossover"]`. The YAML data is loaded
but silently ignored for UART.

**Impact:** If the YAML adds a second UART crossover pair or changes the
function names, the code will not pick up the change. The YAML and the code
are decoupled for UART.

### Gap 1: Non-deterministic set iteration order (low impact, but worth noting)

`shared_functions` is a Python `set`. Iteration order varies across Python
runs (especially across Python versions or hash randomisation). For the current
logic, this has no correctness impact — each function produces an independent
net. However, if future logic adds an early-exit or priority tie-breaking
between functions, set ordering would become a source of non-determinism.

**Recommendation:** Use a list or ordered dict to define function precedence
if ordering ever matters.

### Gap 2: Multiplexed pins — normalizer must pick one protocol

On many microcontrollers a physical pin can serve as either `SCK` (SPI) or
`SCL` (I2C) depending on firmware configuration. `PinDefinition.normalized_function`
is `Optional[str]` — it holds exactly one value. The pin normalizer (P2) must
choose one protocol for the pin. If it picks `SPI_CLOCK`, the pin joins the
`SPI_SCK` net; its I2C capability is invisible to `net_assigner`. No flag,
no warning, no alternate-function tracking.

**Impact:** A component that the designer intends to use as an I2C controller
could have its SCL pin placed on the SPI bus if P2 normalises `SCL` → `SPI_CLOCK`
(e.g. due to alias ambiguity). `net_assigner` will follow that choice silently.

**Relevant alias from canonical_functions.yaml:**
```yaml
CLK: SPI_CLOCK   # raw "CLK" maps to SPI, not I2C
SCK: SPI_CLOCK
SCLK: SPI_CLOCK
SCL: I2C_CLOCK   # raw "SCL" maps to I2C
```
These are distinct so correct disambiguation is possible, but the
`alternate_functions` field in `PinDefinition` (which could carry both
`SPI_CLOCK` and `I2C_CLOCK`) is never read by `net_assigner`.

### Gap 3: I2C has no unique functions — single shared bus assumed

```yaml
I2C:
  shared: [I2C_DATA, I2C_CLOCK]
  unique: []
```

All I2C devices — regardless of their I2C address — are connected to a single
`I2C_SDA` and `I2C_SCL` net. This is correct for standard I2C topology (one
bus, address-based device selection). However, if a design has two separate I2C
buses (e.g., main bus and isolated sensor bus), both would be collapsed onto the
same two nets. There is no mechanism to disambiguate I2C bus 0 from I2C bus 1.

---

## Summary

| Question | Answer |
|---|---|
| Does code handle SPI + I2C on same component? | ✅ Yes — protocols are fully independent |
| Do I2C pins depend on SPI processing order? | No — each function is an independent key |
| Does "first protocol match" block later protocols? | No — no early exit in shared loop |
| Are there actual bugs? | Yes — `uart_group` is a dead variable (Bug 1) |
| Are there design gaps? | Yes — multiplexed pins, no multi-bus I2C support |
