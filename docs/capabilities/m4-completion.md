# M4 integrated completion checkpoint — 2026-10-11

M4 remains open before layout. The retained packet combines recovered original
sources, exact purchasing candidates, the real nine-interface circuit and the
full cross-compiled firmware. It is an engineering checkpoint, not a routed or
manufacturing-ready board.

The original `design.json`, `engineering.json`, `sources.lock.json`,
`candidate-topology.json` and `checklists/.../candidate-circuit.json` are
byte-identical to their committed historical baselines. The revised target
uses `benchmarks/stm32-communications/qualified-design/` (design, engineering,
sources and its own `sources.lock.json` with the recovered ST originals). Its
inputs are `candidate-topology-qualified.json` and
`candidate-circuit-qualified.json`; `*-presupport.json` is the pre-support base
that support qualification patches. The changes are MAX3232IDWR wide DW,
8 MHz HSE bypass / PLL6 / 48 MHz CPU / 24 MHz APB1 / 48 MHz USB, 20 MHz
external CAN clocks, SPI1/2 6 MHz and external SPI 750 kHz.

Current integrated circuit: 141 components, 57 part types, 99 named nets, all
nine interfaces. KiCad 10.0.6 ERC reports every severity with zero violations
under two stated qualifications. First, KiCad's four default-ignored checks
(`single_global_label`, `four_way_junction`, `simulation_model_issue`,
`footprint_filter`) stay ignored under the audited allow-list. Second, three
engineering supply-drive markers on `/5V_RAW`, `/3V3` and `/GND` declare the
external input, the buck output and the return. The exported netlist endpoint
and explicit NC sets match exactly. This proves schematic consistency. It does
not substitute for PCB parity or DRC. Sealing and verification re-run ERC on the retained schematic bytes and
require the same result. 

The actual ARM build uses 34,708 bytes Flash and 17,160 bytes RAM, including
8,192 bytes reserved stack. The conservative stack bound is 5,856 bytes. It is
rebuilt from the retained GCC `-fstack-usage` output (`stack-usage.txt`), and
every linked compiled C function must have a frame row. Details are in
[the firmware report](m4-firmware-complete.md).

## Pre-layout blockers reconstructed by the sealed packet (9)

The completion reader derives every gate from verified sub-packets. Mating fit,
selected-voltage current limits, the review outcome and the feasibility gates
are reconstructed rather than read from authored flags. Sub-packet blockers
propagate unless a named completion check supersedes them.

- `AGGREGATE_CPU_IRQ_SERVICE_BOUND`: source timeouts bound each transaction,
  while the queue model assumes a complete pass within 2 ms. Supply an
  independent static WCET proof for the selected ELF/clock/interrupt model, or
  real instrumented timing under the declared workload.
- `SELECTED_VOLTAGE_CURRENT_LIMIT_QUALIFICATION`: the TPS25947 ILIM table is
  characterized at VIN = 12 V. It becomes a guarantee only with a hash-bound
  vendor applicability document (`vendor_applicability`) or matching-voltage
  characterization. WIZ startup/full-traffic current must stay below the branch
  minimum.
- `WIZ550IO_SOCKET_MATING_FIT`: requires `mating_qualification` records (a
  dimensioned manufacturer drawing, or a human-confirmed physical measurement)
  for both the module post/insertion and the finished host socket hole.
- `CIRCUIT:POWER_THERMAL`, `FEASIBILITY:POWER_THERMAL`: loaded rail, buck loss
  and board thermal evidence. The support thermal model is conditional, not a
  worst-case proof.
- `CIRCUIT:SILICON_ERRATA`, `FEASIBILITY:ERRATA`: selected silicon revision and
  implemented ES096 I2C/USB workarounds.
- `CIRCUIT:USB_UNPOWERED_ATTACH_INJECTION`, `CIRCUIT:INPUT_AND_HEADER_PROTECTION`:
  the support topology addresses these, but no reconstructed review or
  measurement closes them yet.
All 116 `required_fact_ids` now have hash-bound, unconfirmed fact records.
Support pinout/qualification records are derived per catalog type by
`verify_support`. PCB features bind to their frozen footprints. The circuit
integration adds `MCP2518FD-E_SL:sdo-high-z` (DS20006027B Table 7-6 p81, from
the earlier agent source review; not re-read by a person) and the WIZ550io
pinout/qualification facts. An unrecorded id would still raise
`REQUIRED_FACT_RECORDS`.

After these: `NATIVE_BOOTSTRAP_PLACEMENT_ROUTING_DRC_EXPORT`. The release-only
blockers are `CRITICAL_FACT_CONFIRMATION`, `LICENSE_REVIEW` and every pending
critical confirmation listed in the sealed report. M5 still needs actual board, silicon and ELF identity;
rail/transient/thermal and signal/clock-load validation; errata behavior; peer
traffic and complete logs. No confirmation is inferred from agent review.

## Independent review

One independent read-only whole-change review found 10 Important and 4 Minor
issues against the first, unsealed `runs/m4/completion-2026-10-11`. That packet
is retained unchanged as pre-review evidence and does not verify. Fixes include
RED-to-GREEN regressions for forged mechanical, current-limit, feasibility,
stack-row and review records, plus blocker and fact propagation. F11 is fixed:
sealing and verification re-run KiCad ERC (`--severity-all`) on a copy of the
retained schematic, and the result must equal the retained report. The
retained `native/commands.json` records the ERC call without
`--severity-all`, although its report includes exclusions. The re-run is the
binding evidence. F14 is fixed: `cross_bindings` checks the engineering
`design_id`, design MPNs, the WIZ550io revision, all 45 MCU pin nets (with
declared aliases) and the firmware GPIO configuration (25 pins) against one
design revision. F13 is declined: intermediate 2026-10-10 runs such as
`source-qualified-final-2026-10-10` and `erc-closed-2026-10-10` are superseded
and no longer verify under current code. No second independent review was
dispatched after the fixes.

## Retained evidence and verification

Sealed packet: `runs/m4/completion-2026-10-11-r3/`. It supersedes `-r2`, which was sealed before the fact, ERC re-run and cross-binding fixes and no longer verifies under current code. Its contents are the
circuit, fabrication and mechanical packets; feasibility rebuilt from
`runs/m4/full-firmware-2026-10-11-r2`; `independent-review.json`, bound to the
circuit and sub-packet hashes; and `completion-integrity.json`. Publisher
originals remain in ignored local runs; retrieval confers no redistribution
approval.

```sh
.venv/bin/python -m pcb_harness.orchestration.m4 \
  --benchmark benchmarks/stm32-communications/qualified-design \
  --checklist checklists/stm32-communications/resources.json \
  --sources <source snapshot> \
  --source-lock benchmarks/stm32-communications/qualified-design/sources.lock.json \
  --engineering benchmarks/stm32-communications/qualified-design/engineering.json \
  --full-firmware <full firmware build> \
  --full-firmware-sources benchmarks/stm32-communications/firmware-full \
  --output runs/m4/<new feasibility>

.venv/bin/python -m pcb_harness.orchestration.m4_completion \
  runs/m4/completion-2026-10-11-r3 --verify
```

Sealing returns exit 2 while M4 is incomplete. Verification returns 0 only for
matching retained evidence; this exit code does not declare layout,
manufacturing or hardware acceptance.
