# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

PCB Harness is a KiCad-grounded PCB design harness (target: a STM32F103C8T6 board with nine communication interfaces). The harness supplies a Kernel and local MCP tools; **the model lives in the host** (Codex/Claude via subscription). The harness never makes inference calls, never requires a provider API key, and never runs an autorouter: every geometry path has to come from caller intent.

The authoritative design doc in this repository is `PCB Harness — Development Roadmap.md` (mostly in Thai). Milestones M0→M5 are gated. Per-milestone execution plans live in `docs/superpowers/plans/`, and evidence/status ledgers live in `docs/capabilities/m*-progress.md` (plus the M4 sub-reports). Before claiming a milestone's status, read its ledger. Do not infer status from code.

## Commands

Requires Python 3.11+, KiCad 10.0.6 on macOS (`/Applications/KiCad/KiCad.app`), and the venv in `.venv`. Use `.venv/bin/python -m ...`; console-script shebangs break when the project moves.

```sh
.venv/bin/python -m pip install -r requirements-mcp.lock
.venv/bin/python -m pip install -e '.[test,mcp]' --no-deps --no-build-isolation
.venv/bin/python -m pytest -q                                # full suite, ~2 min, ~680 tests
.venv/bin/python -m pytest -q tests/test_kernel.py::test_name # single test
.venv/bin/python experiments/kicad-ipc/verify_fixture.py      # real DRC/ERC/parity/SVG on committed fixture
```

`pytest` config (`pyproject.toml`) adds `src` and `experiments/kicad-ipc` to `pythonpath`. Some tests skip when a local-only artifact is missing (e.g. the ARM toolchain under `runs/m4/toolchain/`, or a sealed packet under `runs/m4/`). A skip is not a pass.

M4 orchestration runners are `python -m pcb_harness.orchestration.<module>` (`m4`, `stm32_circuit`, `core_assets`, `core_pin_evidence`, `source_completion`, `support_qualification`, `firmware_complete`, `m4_completion`). Every runner needs a **new** `--output` directory under `runs/`. **Exit 2 means evidence was captured but the gate is closed.** It does not mean the step passed. Exact reproduction commands are in `benchmarks/stm32-communications/README.md` and the matching `docs/capabilities/m4-*.md`.

## Architecture

- **Kernel** (`kernel.py`, `contracts.py`, `memory.py`, `ipc.py`, `safety.py`, `native_reports.py`): a single-writer action API. Every query returns a `revision`. `execute(name, args, expected_revision, action_id, mode)` enforces revision/lock checks, makes action-ID replay idempotent, uses strict-mode checkpoint restore on new DRC findings, and journals actions durably. A latched `RECOVERY_REQUIRED` blocks writes. There is no auto-retry and no recovery-clear API, by design. Backends are `memory.py` (limited test double: no flip/zone) and `ipc.py` (native KiCad IPC via `kicad-python`). See `docs/kernel.md`.
- **MCP** (`mcp_server.py` STDIO entry `pcb-harness-mcp`, `mcp_service.py`, `run_envelope.py`, `rendering.py`, `capture.py`): 14 tools wrapping the Kernel, plus calibrated PNG board/region views. The run envelope is frozen at launch (default 300 admitted writes / 20 min). Rejected and replayed writes count against it, and reconnecting does not reset it. See `docs/mcp.md`.
- **Circuit (M3)** (`circuit/`): offline JSON schemas in `circuit/schemas/` (package data), plus hash-bound source/asset provenance, review, KiCad s-expression writer/symbol flattening and native schematic/PCB bootstrap. `circuit/bundle.py` has the shared strict `read_json`/`sha256`/`resolve_local` helpers that every packet uses.
- **Fabrication** (`fabrication/`): a profile/capability model and a saved-file custom-rule compiler with native negative tests.
- **Orchestration (M4)** (`orchestration/`): evidence producers for the real STM32 target. Each one copies its inputs into its output run, writes `report.json` and an `integrity.json` hash inventory, and provides a `verify_*` that **reconstructs the report from the underlying evidence** instead of trusting pass flags. `m4_completion.py` aggregates the circuit/feasibility/fabrication/mechanical sub-packets plus `independent-review.json` into a sealed `completion-integrity.json`.
- **Data inputs**: `benchmarks/stm32-communications/` holds design/topology/source locks/firmware sources. `qualified-design/` is the revised target, and the original `design.json`/`engineering.json` stay the historical baseline. `checklists/stm32-communications/` holds the independently supplied checklists. `fixtures/capability/` is immutable.
- **Experiments**: `experiments/kicad-ipc/` and `experiments/mcp/` are native probe and smoke scripts that need a live PCB Editor with the KiCad API enabled.

## Hard rules (from README/CONTRIBUTING/kernel docs)

- Make native edits only in a fresh scratch project under `runs/`, selected by exact project/document path. Confirm the IPC socket: `api.sock` may belong to KiCad Manager, while PCB Editor uses `api-<pid>.sock`. Never retry an uncertain write, clear a journal, or rewrite old run identities to make something pass.
- Never fabricate human confirmations, hardware measurements or manufacturer applicability. Never promote typical or absolute-maximum values into guaranteed or operating limits. Never hand-flip a gate flag (`layout_allowed`, `release_eligible`, `milestone_complete`). Unknown stays unknown.
- Never silently replace source hashes. A re-fetch needs a new lock entry. Never alter historical packets. Publisher PDFs stay in ignored `runs/` and are not redistributed.
- Behavior changes need observed RED→GREEN regression tests. Test MCP behavior through the real SDK/STDIO client, not mocked success. When reporting results, keep Memory/protocol tests, native KiCad checks, host-integration runs and hardware tests separate.
- In a sandbox, KiCad CLI `--schematic-parity` can abort during GUI init. Treat that as an environment failure, not a board result.
- Commit locally; push only when the user asks. Project code is Apache-2.0; third-party files keep their own licenses (`THIRD_PARTY.md`, `docs/open-source.md`).

