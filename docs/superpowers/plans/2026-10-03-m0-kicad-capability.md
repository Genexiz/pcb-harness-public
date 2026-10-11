# M0 KiCad Capability Execution Plan

> Execute inline using superpowers:executing-plans. Disposable probes establish contracts before production Kernel implementation.

**Goal:** prove footprint/copper mutations, commit/rollback, saved-file verification and rendering on installed KiCad 10.

**Spec:** PCB Harness — Design Spec (v2).md

**Constraints:** no autorouter/SWIG; only scratch board modifications; verify document identity; preserve original project; pin package versions; unsupported APIs remain unsupported.

## Tasks

1. Capture actual version/help/dependency artifacts. Configure project-local venv and development branch. No existing code/tests at baseline.
2. Build a three-resistor/two-net native project fixture with known correct pin mapping. Tests invoke real CLI for ERC/DRC/parity. Known-bad copies introduce short, clearance, width, open connection and footprint mismatch.
3. Bind IPC to the exact fixture document; reject wrong/ambiguous board selection. Query footprints/pads/nets. Probe footprint creation, transforms, exact tracks/vias, update/delete.
4. Probe begin/push/drop commits, saved snapshots, revert and explicit re-open. Capture geometry before/after. Check lock semantics, stale read/human edit detection and disconnected-client behavior without touching user projects.
5. Verify custom rules/zone refill against CLI; export SVG with layers/coordinates checked. Capture unsupported method errors instead of inventing workarounds from SWIG.
6. Write capability matrix and recovery limitations; rerun unit/real CLI tests; fresh reviewer checks safety and false-pass paths; commit tested M0 artifacts.

## Review focus

- Wrong document selection must stop before any mutation.
- Process/parse/missing-report errors must never become design pass.
- Partial IPC failure must remain uncertain until readback reconciles board state.
- Newer binding methods may require KiCad patches/new major versions.
- Restoration must cover project settings/rules and preserve unrelated user edits.

Run: `.venv/bin/python -m pytest -q`; integration commands and probe results are captured under `runs/capability/`.
