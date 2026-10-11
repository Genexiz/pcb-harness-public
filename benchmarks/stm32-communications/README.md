# STM32 communications pre-layout benchmark

This is the real-target candidate allocation for M4, not a complete M3 circuit
bundle or a layout-ready board. The MCU and all nine interfaces are preserved.
`design.json` records exact candidate MPNs/packages, default pin assignments,
DMA/EXTI ownership, selected traffic assumptions and engineering power reserves.
The separate resource checklist is agent-reviewed and **not human confirmed**.

Sources and build outputs belong in local ignored `runs/m4/` directories.
Publisher PDFs are not redistributed in the source tree. `sources.lock.json`
freezes eight retrieved publisher snapshots and explicitly records three ST
retrieval failures. The engineering continuation appends a WIZnet dimension
drawing; initial source hashes are preserved. A matching hash proves snapshot integrity, not a reviewed
electrical circuit. Source inspection and limitations are in
`source-inspection.md`. Re-fetching changed documents requires a new lock and
revision review; do not replace hashes silently.

Retrieve sources into a new directory (TLS verification remains enabled):

```sh
.venv/bin/python benchmarks/stm32-communications/fetch_sources.py \
  --output runs/m4/sources/new-retrieval --cafile /etc/ssl/cert.pem
```

`--cafile` is optional and machine-specific; omit it on hosts with a configured
Python trust store. Failed fetches are retained as unavailable; the downloader
does not alter the committed source lock. ST endpoint failures on this host
included timeout/HTTP2 failure and ST community fallback returned HTML, which
was not accepted as a PDF.

The recorded compiler is official Arm GNU Toolchain 13.2.rel1 for macOS arm64.
Archive SHA-256, matching the publisher checksum:
`39c44f8af42695b7b871df42e346c09fee670ea8dfc11f17083e296ea2b0d279`.
Obtain an appropriate toolchain for your OS from
[Arm](https://developer.arm.com/Tools%20and%20Software/GNU%20Toolchain).
The harness never installs it system-wide.

```sh
.venv/bin/python benchmarks/stm32-communications/firmware/build.py \
  --compiler runs/m4/toolchain/arm-gnu-toolchain-13.2.Rel1-darwin-arm64-arm-none-eabi/bin/arm-none-eabi-gcc \
  --output runs/m4/firmware-new

.venv/bin/python -m pcb_harness.orchestration.m4 \
  --sources runs/m4/sources/engineering-2026-10-10 \
  --source-lock benchmarks/stm32-communications/sources.lock.json \
  --firmware runs/m4/firmware-new \
  --engineering benchmarks/stm32-communications/engineering.json \
  --output runs/m4/feasibility-new
```

Output paths must be new. CLI exit **2** means evidence was captured but the
pre-layout gate is closed; it does not mean the board passed. Exit 0 is reserved
for a future complete pre-layout acceptance. Current assessments deliberately
leave full firmware, CPU timing, power/thermal, mechanical, errata, actual
circuit/native and fabrication acceptance unresolved. A complete implementation
of those evidence producers is required before this runner can permit layout.

The firmware is a freestanding **resource probe**, with real CRC/queue code and
chosen buffer/stack reservations. It has no USB/CAN/W5500/UART/I2C driver and is
not a board bring-up binary. No hardware measurements were performed. The
cross-build test skips when its recorded local compiler is absent; the pure
ELF/integrity and host C behavior tests still run. No provider API key is used.

`verify_report(run_path)` checks retained artifact hashes. The run includes
input snapshots, available publisher sources and copied cross-build evidence.
As with M3, this detects drift; it is not a defense against rewriting all owned
artifacts and their hashes together.

`engineering.json` freezes source-specific observations and separate choices:
CAN RX/TX/TEF buffers and timestamps, literal bit timing, rail tolerance targets,
per-device VDD/VIO loads, module screening and17 targeted errata policies.
`--engineering` is optional for compatibility. The runner copies it before
evaluation and integrity-checks the retained copy. Hash binding does not prove
that the agent interpreted the source correctly.

The final continuation report is `runs/m4/engineering-final-2026-10-10/report.json`.
CAN RAM arithmetic passes (Classical384B, FD1280B per2KB controller); firmware
and propagation/TDC remain unknown. Power reserves are3V3=0.572A, direct5V=0.16A
including both CAN VIO loads; typical/no-load/conditional limits never become
full-load bounds. Source format checks reject publisher error HTML disguised
as a PDF, incomplete PDF/PNG envelopes and unsupported formats. These are
envelope checks, not full PDF/image parsing or revision/content verification.
Hash and envelope checks inspect the same frozen bytes, including the retained
source capture. Facts and loads require explicit `supply_domain` (`VDD`/`VIO`;
non-supply facts use null), so a VIO limit cannot certify a VDD load. Power
screening reconciles the complete calibrated inventory, including U8 and its
regulator identity; new devices or regulator choices require reviewed coverage.
See [independent review and limits](../../docs/capabilities/m4-engineering-review.md).

Core pin connections and USB-C/boot/reset/clock/power/protection/termination
policies are in [circuit-draft.md](circuit-draft.md). It is a candidate topology,
not an accepted schematic or complete purchase BOM. Mechanical screening
retains the publisher54/55mm disagreement and unselected connector/socket
envelopes. No complete-board gate is unlocked by the dossier.

The next asset stage is recorded in `core-asset-candidates.json` and
[core asset inspection](../../docs/capabilities/m4-core-assets.md). These are
hash-recorded observations of the installed library, not accepted parts or
redistributed asset files. Exact CAN symbols, inherited-symbol flattening,
the THVD1450DR package correction, module mechanics and support BOM remain
required. Number-set matching does not establish source-reviewed pin identity.

The local preparation runner now produces standalone exact-MPN core assets,
strict M3 parts and an eight-IC/nine-core-instance inventory. It freezes the
source bytes before flattening inheritance and preserves stencil/duplicate EP
shapes. See [preparation and reproduction](../../docs/capabilities/m4-core-preparation.md).
Final real run: `runs/m4/core-assets-final-2026-10-10`; CLI exit2, accepted real-target
assets0. WIZ550io, complete support BOM, pinout/package facts and full circuit
acceptance remain unresolved; this output cannot permit layout.

The [core pin evidence packet](../../docs/capabilities/m4-core-pin-evidence.md)
records explicit manufacturer/symbol aliases and original-source binding.
Run `python -m pcb_harness.orchestration.core_pin_evidence --core <prepared-run>
--source-root <retained-source-directory> --output <new-run>` with the local
environment. Five retained PDFs bind55 candidate pin observations and10 strict
unconfirmed identity facts; STM32 originals and all board gates remain open.
The packet does not approve electrical types, purchasing availability or land
patterns. MAX3232's exact-orderable and narrow-SOIC drawing gaps remain explicit.

The historical review artifact is built from `candidate-topology.json` and the
separately authored `checklists/stm32-communications/candidate-circuit.json`
(byte-identical to their 2026-10-10 baselines). The current integrated circuit
uses `candidate-topology-qualified.json` / `candidate-circuit-qualified.json`;
pass them explicitly with `--topology`/`--checks`.
`python -m pcb_harness.orchestration.stm32_circuit --help` documents the runner.
It preserves the verified core/pin packet, imports original WIZnet Eagle CAD,
and emits the current141-component candidate schematic/CSV with all nine interfaces.
Recovered original sources, exact support and full firmware are integrated;
current native ERC has zero violations (KiCad default-ignored checks and three
declared supply-drive markers) with exact netlist endpoints. Nine pre-layout
blockers remain; see the completion checkpoint.
See `docs/capabilities/m4-completion.md` for the integrated checkpoint and
`qualified-design/` for the explicitly revised clocks and wide-DW RS232 part.
The original design/engineering inputs remain the historical core baseline.
