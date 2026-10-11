# PCB Harness

Standalone KiCad-grounded PCB design harness under development. M0 and the initial M1 scratch Kernel are verified on KiCad 10.0.6. This is not an autonomous PCB designer yet.

This project is intended for **open-source release** under Apache-2.0 (`LICENSE`); third-party files keep their own licenses. See [open-source preparation](docs/open-source.md) and [third-party notices](THIRD_PARTY.md).

Design: [Roadmap](PCB%20Harness%20%E2%80%94%20Development%20Roadmap.md)

## Run the current checks

Requires Python 3.11+ and KiCad on macOS. Original M0 baseline is 10.0.0; current CLI regression is verified on 10.0.6. Paths in this probe intentionally match the installed macOS bundle; portable discovery belongs to the Kernel milestone.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-mcp.lock
.venv/bin/python -m pip install -e '.[test,mcp]' --no-deps --no-build-isolation
.venv/bin/python experiments/kicad-ipc/verify_fixture.py
.venv/bin/python -m pytest -q
```

`verify_fixture.py` runs real DRC with schematic parity, ERC, and SVG export on the committed three-resistor fixture. It writes raw JSON, command/stdout/stderr evidence, hashes and a summary to `runs/capability/cli/`. Runs are ignored by Git; source fixtures and tests are retained.

The scratch circuit uses three parallel passive resistors with two nets. `Harness:Probe_R` is a custom geometric probe footprint, **not a production resistor package**. No part facts or fabrication readiness are implied by this test circuit.

Full tests include known-bad board copies for shorts, clearance, track width, open connections, schematic/PCB mismatches and output pin conflicts. The report reader rejects missing/unknown schemas, missing sections, omitted severities, source mismatch, malformed reports and failed CLI execution. A pre-existing report cannot turn a failed command into pass.

The native custom rule is independently tested with its global width floor lowered. Thresholds use explicit `mm`. KiCad 10.0.0 CLI can silently ignore malformed rule text, so the M0 IPC wrapper still accepts only the exact tested scratch-rule subset. M3 adds a separate saved-file fabrication compiler with native negative tests; it does not relax that IPC guard.

On this Codex sandbox, KiCad `--schematic-parity` requires an approved command outside the sandbox: macOS GUI initialization otherwise aborts the CLI. Run normally from a local terminal, or use the tool's approved execution path. Do not interpret the abort/missing report as a board result.

## IPC probe

1. Run `.venv/bin/python experiments/kicad-ipc/prepare_live_fixture.py` once, then open `runs/capability/live/board.kicad_pcb` in a **separate PCB Editor window**. The committed fixture remains unchanged. The preparation command refuses to overwrite an existing live project.
2. Enable KiCad API under Preferences → Plugins. This is a local API; no MCP service is published.
3. Run:

```sh
.venv/bin/python experiments/kicad-ipc/probe_ipc.py
```

The probe selects the exact scratch document by resolved project/file path and rejects ambiguous or unrelated documents before modifying anything. The default socket is `ipc:///tmp/kicad/api.sock`; specify `--socket` if the scratch editor uses another socket. Do not choose a socket based only on the fact that it connects.

Probes exercise explicit coordinates, native commits, readback and restoration. They do not invoke an autorouter or SWIG. `native_flip_items` may be unsupported on KiCad 10.0.0: the installed binding 0.8.0 was built against 10.0.6 and capability detection is required per method.

Only run on the scratch fixture, without human edits during mutation probes. The probe is experimental and is not the production multi-writer/checkpoint recovery system. If a rollback cannot restore the baseline, it stops before further mutations.

Multiple KiCad applications can expose different sockets: in the continuation run, `api.sock` belonged to KiCad Manager and rejected `GetOpenDocuments`; PCB Editor used `api-<pid>.sock`. After restarting PCB Editor, discover its new socket and confirm the exact document again. Never retry a mutation just because a connection failed.

`probe_lost_reply.py --socket <confirmed socket> --output <new run directory>` sends one native commit and closes the connection before receiving its reply. It retains the uncertain operation record, reconciles through an independent client and restores only the exact expected scratch state. It does not prove recovery from an OS crash or arbitrary concurrent edits.

`probe_render.py --svg <native SVG> --geometry <IPC baseline.json> --output <new run directory>` validates the M0 fixture's pad centers, copper endpoints and rectangular outline, then creates an R1 crop with an explicit mm viewBox. This calibration is specific to the observed KiCad 10.0.0 fixture output.

Revert guards inspect the complete serialized PCB and related file hashes; conflict/readback failure leaves an explicit uncertain outcome and attempts a recovery copy. Checks cannot eliminate a race with another writer or observe every unsaved project-setting edit, so the single-writer requirement remains in force.

## Board images

MCP now provides whole-board and region PNG tools, with layers, revision and calibrated mm/pixel metadata. Images are returned directly as MCP ImageContent; no model API key is needed. Memory diagrams remain labelled test-only. Native saved-fixture renders and modern/legacy image delivery are verified.

A separate editor-window capture tool is implemented for macOS with explicit instance/window binding and existing Screen Recording permission. Actual live render/capture and host vision analysis are still unverified in the current environment. See [visual tools](docs/mcp.md#visual-tools-14-tools-total) for parameters, setup and current limits.

## Current status

M0's core capability gate is verified: native geometry edits, commit/revert, save/reopen, custom rule negatives, zone fill, saved-board DRC/ERC/parity and fixture SVG calibration. Manual GUI edits and a lost commit reply were also tested. See [capability report](docs/capabilities/kicad-10-macos.md) for exact evidence and remaining recovery limits. The initial M1 Kernel is documented in [Kernel guide](docs/kernel.md); its current native acceptance status is separate from the M0 completion claim.

The primary workflow is **Subscription-driven local MCP**: Codex signed in with ChatGPT calls the MCP tools, which use the same Kernel and local KiCad. Harness will not require a model API key or make its own inference calls in this workflow. The local STDIO MCP server is implemented and SDK/protocol-tested; see [MCP guide](docs/mcp.md). Native mutations/checkpoints require the exact connected scratch backend on verified KiCad 10.0.6; other versions stay gated. M2 single-agent routing feasibility passed 4/5 native runs in `runs/routing/m2-2026-10-09-r3`; see [M2 evidence and limits](docs/capabilities/m2-progress.md). API-key providers are optional future work only when requested.

KiCad API means the local IPC command interface, not an LLM API key. Host subscription access/limits remain separate from Kernel action/time budgets. Host model tokens/costs not exposed to Harness must be marked unavailable. Do not commit credentials or logs containing them.


MCP runs freeze their action/time limits at launch (default 300 admitted write requests and 20 minutes from the first write). Rejected/replayed writes count, reconnect does not reset them, and exhausted runs retain read/verification/image tools. See [run-envelope semantics and recovery limits](docs/mcp.md#frozen-run-envelope). The passing M2 runs used six admitted writes and 232.850–240.979 seconds each. One run stopped on a lost checkpoint reply with `RECOVERY_REQUIRED` and was not retried.

M3 now provides strict requirements/circuit schemas, hash-bound source/parts auditing, independent upstream review, fabrication coverage/rules and readable native schematic/PCB bootstrap. Post-review acceptance passes eight circuit negatives and eight native rule negatives, with clean ERC/geometry/parity and exact exported netlist on the unrouted positive fixture; seven review findings are fixed and 373 tests pass. See [M3 evidence and limits](docs/capabilities/m3-progress.md). Real part/fabrication confirmations remain release blockers; M4 real-target feasibility is next.

M4 now has a real STM32F103C8T6 candidate pin/DMA/EXTI allocation, bounded SPI wire-time and power estimates, source snapshots, and a cross-compiled resource probe with hash-bound ELF/map evidence. Complete interface firmware, power/thermal, mechanical, errata and actual circuit/native gates remain unresolved; layout and release stay closed. See [M4 progress and required evidence](docs/capabilities/m4-progress.md) and [benchmark reproduction](benchmarks/stm32-communications/README.md).

The M4 engineering continuation adds source-bound CAN FIFO/timestamp/bit-timing calculations, separate transceiver VDD/VIO loads, supply-range screening, mechanical conflicts and17 planned errata policies. A [concrete circuit draft](benchmarks/stm32-communications/circuit-draft.md) covers all nine interfaces. Independent review fixes enforce supply-domain applicability, complete candidate inventory and atomic source-byte checks; see [review and limits](docs/capabilities/m4-engineering-review.md). This remains a pre-layout draft; exact support BOM/assets, complete drivers, thermal/module limits and native circuit acceptance are still required.

The [core asset preparation runner](docs/capabilities/m4-core-preparation.md) now freezes original geometry, creates six standalone exact-MPN symbol/footprint candidates and an eight-IC/nine-core-instance BOM, and verifies each derivative against its captured source. Independent review fixes package/document admission and per-part/BOM semantic linkage; 528 tests pass. Pinout/package facts, WIZ550io assets and the complete support BOM remain unresolved; layout stays closed.

The [core pin evidence packet](docs/capabilities/m4-core-pin-evidence.md) now
binds authored manufacturer/symbol aliases to the saved assets and original
publisher revisions:55 pins across five sourced IC types, plus an MCU inventory
whose original PDF is still unavailable. Ten M3 identity facts remain
unconfirmed. Source binding does not approve electrical types, land patterns,
exact-orderable availability or the complete circuit; layout remains closed.
One review finding is fixed; the final regression suite passes561 tests.

The [real-target review schematic](docs/capabilities/m4-circuit-review.md) now
contains104 components and all nine interfaces, with a manufacturer-CAD-derived
WIZ550io candidate. Native endpoint sets match73 nets/19 NC contacts. ERC still
has four errors and exact support/source/firmware/thermal gates remain open;
this candidate is not an accepted PCB or completed M4.

The [integrated M4 checkpoint](docs/capabilities/m4-completion.md) adds a
141-component circuit with zero ERC violations (KiCad default-ignored checks and
three declared supply-drive markers stated) and nine-driver firmware at
34,708 B Flash / 17,160 B RAM. After an independent review and fixes, the sealed
`runs/m4/completion-2026-10-11-r3` reconstructs 9 open pre-layout blockers:
timing, current-limit applicability, socket fit, power/thermal, errata and
USB/protection. All required facts are recorded but unconfirmed. Layout remains closed.
