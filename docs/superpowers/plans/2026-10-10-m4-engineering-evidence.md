# M4 engineering evidence continuation plan

> **For agentic workers:** Use superpowers:executing-plans inline and one independent whole-change review. The explicit request to continue M4 preserves the approved v2 target and execution method.

**Goal:** Turn source inspection into reproducible CAN controller, supply and mechanical calculations and a concrete interface circuit draft, retaining named missing evidence before layout.

**Architecture:** Add an optional strict engineering dossier to the existing M4 runner. Every document fact carries its source ID, original-file hash and locator; engineering choices remain choices. Source integrity, numerical feasibility and full-board acceptance are distinct outputs. Existing reports without a dossier remain valid.

**Tech Stack:** Python/jsonschema, retained publisher PDFs, existing hash-bound M4 report runner, Arm resource probe.

**Spec:** `PCB Harness — Design Spec (v2).md` sections 3, 8, 9; `PCB Harness — Development Roadmap.md` M4.

## Global constraints

- STM32F103C8T6, LQFP48, 64 KB flash / 20 KB RAM; nine interfaces, external MCP2518FD controllers, WIZ550io retained.
- Existing non-main checkout preserves native evidence paths. No native mutation, provider keys, route search, merge, push or manufacturing request.
- Regulated external 5 V; USB-only power unsupported. At most 100 x 100 mm, four mounting holes.
- Agent-reviewed facts are not human confirmation. Typical/no-load current, initial regulator accuracy and a JEDEC theta-JA are not whole-board maximum/thermal proof.
- Retain failed original-source retrieval and document disagreements. Neither caller flags nor a dossier can unlock full firmware/circuit/fabrication prerequisites.

## Review focus

- Missing/different parts, omitted rails or device instances must invalidate engineering coverage.
- CAN RX timestamp storage, TX/TEF storage, alignment and exact bit rate constraints must be accounted independently of prior wire estimates.
- Source hash/format drift and changes while capturing a dossier must not yield false source-backed calculations.
- A smaller module body, missing connector envelope or unresolved source conflict must not pass mechanics.
- Firmware errata policies are planned requirements; flags must never prove implemented firmware or actual silicon revision.

### Task 1: Reject false publisher snapshots

Files: `src/pcb_harness/orchestration/m4.py`, `tests/test_m4_feasibility.py`.

Interfaces: `audit_sources(spec_path, source_root, lock_path)` retains its result fields; `hashes` contains only hash-matching PDF/HTML snapshots of the correct type.

- [x] Add a regression with HTML bytes named `.pdf` and a matching hash; assert `integrity_passed == False` and the ID in `unavailable_or_drifted`.
- [x] Run `.venv/bin/python -m pytest tests/test_m4_feasibility.py -q`; expected RED on that false PDF.
- [x] Check `%PDF-` signature and an EOF marker for PDFs, HTML markup for HTML; keep unrecognized formats unavailable. Synthetic test fixtures must be visibly test-only but satisfy this contract.
- [x] Run the same command; expected GREEN. Commit the scoped source audit change.

### Task 2: Assess strict source-bound engineering dossier

Files: `src/pcb_harness/orchestration/engineering_evidence.py`, `tests/test_stm32_engineering.py`.

Interfaces: `assess_engineering(design, dossier, sources, source_lock)` returns `controllers`, `power`, `mechanical`, `errata`, source issues and `human_confirmed=False`. Source inputs are the frozen audit result and lock manifest from Task 1. Later Task 3 snapshots the dossier before calling it.

- [x] Test independent literal CAN memory totals (Classical 384 / FD 1280 bytes), two controllers required, RX capacity matching scheduling, timestamp allowance, 4-byte boundaries, 2048-byte exhaustion, 500 kbit/s and 2 Mbit/s exact rates, invalid SJW, 40 MHz clock proof.
- [x] Test omitted load/rail, duplicated source IDs, changed source digest, typical/no-load current staying unresolved, rail tolerance violating operating ranges, quantity mismatch and source applicability.
- [x] Test oversize module, missing connectors, 54/55 mm disagreement, removed errata item, mismatched design ID, nonfinite/boolean input and unknown/extra fields.
- [x] Run `.venv/bin/python -m pytest tests/test_stm32_engineering.py -q`; expected RED on missing evaluator.
- [x] Implement strict schema plus pure calculations. Controller object bytes: RX=8+payload+(timestamp?4:0), TX=8+payload, TEF=8+(timestamp?4:0), all multiplied by their independent slot count. Rates use `sysclk/(brp*(1+tseg1+tseg2))`; SJW<=tseg2. Power retains separately documented conditional currents and engineering reserves. Mechanics is screening only until all revision/drawing/courtyard evidence exists.
- [x] Run targeted M4 tests; expected GREEN. Commit evaluator and tests.

### Task 3: Populate real evidence and retain a fresh report

Files: benchmark `engineering.json`, `circuit-draft.md`, `source-inspection.md`, `README.md`; M4 runner/tests, progress/review docs, roadmap and root README.

Interfaces: optional `engineering_path` trailing parameter of `run_feasibility`, `--engineering` CLI argument; report `engineering` field references the copied dossier. `verify_report` requires that copy when the report contains engineering evidence.

- [x] Test captured dossier survives original edit, its removal/tamper is detected, unavailable sources remain named, and complete-looking caller data cannot promote layout/release.
- [x] Run targeted tests RED; snapshot `engineering.json` before assessment and integrate results. Keep all full-board gates closed; invalid controller arithmetic adds `CONTROLLER_CONFIG`.
- [x] Freeze real source-backed conditional limits, exact core pin connections, two FIFO/bit timing configurations, regulator/passive requirements, WIZ headers and unresolved drawing conflict. Record concrete USB-C/reset/boot/protection/termination/header policies and remaining exact support-part/asset work.
- [x] Retain new source drawing in a new ignored run directory and fresh source manifest/lock, without silently changing prior locks or claiming ST retrieval success.
- [x] Run real M4 acceptance in `runs/m4/engineering-2026-10-10`; expected exit 2 with valid artifact integrity and named unresolved prerequisites.
- [x] Run `.venv/bin/python -m pytest -q`, escalating native tests if needed; expected all tests GREEN. Request one independent read-only review, repair Important findings with RED-to-GREEN regressions, record rulings and limitations, commit verified work locally.

## Completion boundary

This continuation completes an engineering evidence producer and actual target draft. Full M4 remains open while complete firmware/native circuit/mechanical/fabrication or source/thermal evidence is unknown. Follow-on work is explicit in the retained report; physical bring-up belongs to M5.
