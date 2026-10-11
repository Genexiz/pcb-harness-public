# M4 exact core asset preparation plan

> **For agentic workers:** Use superpowers:executing-plans inline, followed by one independent whole-change review. The user explicitly authorized this next asset/BOM stage after seeing its scope.

**Goal:** Produce standalone exact-MPN assets and the nine-instance core BOM from the inspected library, with reproducible provenance and explicit missing support/module evidence.

**Architecture:** A pure inheritance flattener preserves symbol geometry and pin identities. A local preparation runner verifies candidate/library/footprint hashes, freezes inputs, writes exact-MPN symbols/footprints and strict M3 parts, then audits the generated assets. This is structural asset preparation, not electrical circuit approval.

**Tech Stack:** Existing Python S-expression parser, strict M3 schemas and asset auditor; installed KiCad 10.0.6 libraries; local ignored run artifacts.

**Spec:** `PCB Harness — Design Spec (v2).md` sections 3/4/9; `docs/capabilities/m4-core-assets.md`.

## Global constraints

- Preserve STM32F103C8T6 and all nine interfaces; both external CAN controllers remain MCP2518FD-E/SL.
- Preserve full MPNs and package-specific pin/pad mapping; do not silently substitute template devices.
- No native editor writes, routing search, provider keys, merge, push or fabrication request.
- Library derivatives remain local run artifacts with attribution/license provenance; publisher PDFs are not redistributed.
- Number-set agreement and source inspection are not human confirmation. Layout/release/M4 completion remain false.
- The six IC types represent eight IC instances; WIZ550io adds the ninth core instance but remains an unresolved asset.

## Review focus

- Inherited property/geometry precedence must not omit or duplicate pins; ambiguous geometry and cycles fail closed.
- Changed library or footprint bytes, unsafe paths and mismatched declared candidate pins must be rejected before generating a misleading artifact.
- Exact-MPN aliases must not preserve a different device's Value/default footprint or pretend its electrical parameters were reviewed.
- Stencil and duplicate exposed-pad shapes must survive preparation and audit; the source libraries remain unchanged.
- Missing module/support BOM and datasheet/license approval remain named blockers even when all six structural assets pass.

### Task 1: Flatten one symbol without changing electrical geometry

Files: `src/pcb_harness/circuit/symbols.py`, `tests/test_symbol_flattening.py`.

Interface: `flatten_symbol(library, name, new_name, properties=None)` consumes the parsed library and explicit property overrides; returns one standalone symbol node without `extends`. The input tree is unchanged.

- [x] Test multilevel inheritance: child Value wins, parent footprint is retained unless explicitly overridden, inherited units are renamed to the output prefix and all pins/coordinates/types remain equal.
  ```python
  result = flatten_symbol(library, "Child", "Exact", {"Value": "FULL-MPN"})
  assert not children(result, "extends")
  assert child(children(result, "symbol")[0], "pin")[1] == "input"
  assert library == original
  ```
- [x] Test missing/cyclic parents, duplicate root symbols/properties, unsupported child geometry and unsafe output names. Run `.venv/bin/python -m pytest tests/test_symbol_flattening.py -q`; expect missing-module RED.
- [x] Resolve ancestry with a visited set; choose nearest properties/top-level attributes, preserve geometry only from its defining ancestor, rename child unit prefixes, deep-copy all nodes and reject ambiguous/malformed inheritance. Run the tests GREEN and commit.

### Task 2: Freeze exact core assets and core BOM

Files: `src/pcb_harness/orchestration/core_assets.py`, `tests/test_core_asset_preparation.py`, benchmark README/progress and asset-preparation docs.

Interface: `prepare_core_assets(candidate_path, library_root, output)` creates a new local run directory. It captures candidate metadata and selected original symbol-library/footprint bytes, verifies their recorded hashes/pins, writes `parts.json`, `core-bom.json`, `report.json`, exact-MPN assets and `integrity.json`; returns a report. `verify_core_assets(output)` validates retained hashes and re-audits captured parts. CLI takes `--candidates`, `--library-root`, `--output` and exits2 because full-board prerequisites are unresolved.

- [x] Tests use a visibly synthetic library/candidate and literal two-pin part: standalone assets pass `load_part_assets`, generated Value/footprint identify the exact selected MPN, old input edits cannot alter the retained audit, reused outputs and drifted hashes/pins/paths fail.
  ```python
  report = prepare_core_assets(candidates, libraries, output)
  assert report["structural_assets_passed"]
  assert not report["layout_allowed"]
  assert verify_core_assets(output)
  ```
- [x] Add duplicate-ID/MPN/ref and package/template mutation negatives; report/parts removal and tampering must fail verification. Run tests RED before implementing the runner.
- [x] Snapshot and validate all inputs before flattening. Build one local namespace with exact sanitized MPN names, explicit Value/Footprint/Datasheet properties, source license identifiers and observed pins with null unreviewed operating ranges. Reuse the strict parts schema and existing auditor. Every part declares required pinout/package facts; unavailable facts are never fabricated. BOM expands U2/U3 and U4/U5 into their actual instance refs and keeps missing M1/module plus all support categories explicit.
- [x] Run targeted tests GREEN; generate actual artifacts in `runs/m4/core-assets-2026-10-10` and audit all six standalone IC assets, duplicate EP and stencil shapes. Verify source hashes are unchanged. The CLI must return2 and keep complete-circuit/firmware/power/mechanical/errata/fabrication/source gates closed.
- [x] Run full suite outside sandbox for native KiCad tests if needed, build the wheel and request one independent read-only review. Repair Important findings with RED→GREEN cases, record remaining prerequisites and commit the verified work.

## Completion boundary

This plan completes exact core-asset preparation and an explicit eight-IC/nine-core-instance BOM inventory. It does not claim a complete support BOM, accepted WIZ550io footprint, source-reviewed complete circuit or firmware. Those remain subsequent M4 work and cannot be bypassed by this runner.
