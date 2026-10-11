# Initial M1 Kernel

This is a single-writer, scripted Kernel slice. It is not an autonomous designer or a fabrication release verifier. Native actions are restricted to a complete scratch project under this repository's `runs/` directory with the audited M0 rule subset and one rectangular outline.

## Setup after moving the project

Use Python 3.11+ and the installed KiCad 10.0.6 on macOS. A moved venv's editable package path needs reinstalling; using `python -m` avoids old console-script shebang paths.

```sh
.venv/bin/python -m pip install -r requirements-m0.lock
.venv/bin/python -m pip install -e . --no-deps --no-build-isolation
.venv/bin/python -m pytest -q
```

## Kernel contract

Queries `summary()`, `get_footprint(ref)`, `net_info(net)` and `list_unrouted()` return a revision. Query results are rejected if the board changes during readback. All geometric quantities use explicit mm/degrees; net names are canonical KiCad names.

`execute(name, args, expected_revision=..., action_id=..., mode='strict')` returns `ok`, `before_revision`, current/after `revision`, `changed_ids`, `drc_delta`, warnings and structured errors. Use the queried revision and a new unique action ID. Immediate replay of the same ID/intent/current state returns the recorded result without editing again; different intents conflict, and historical results invalidated by later changes return `ACTION_RESULT_STALE`.

Supported initial actions: place/move/rotate footprint, explicit track polyline, through via, track deletion, and native zone create/fill. Native `flip_footprint` and placement side changes are gated to KiCad 10.0.6+ in the tested 10.0 family. They invoke native flip rather than setting the footprint layer alone. The limited Memory backend deliberately has no flip/zone capability.

Strict mode restores the checkpoint when new/changed geometric findings appear. Permissive mode commits and reports the actual delta. Unconnected/dangling copper is separate temporary connectivity evidence; acceptance does not imply complete connectivity or release readiness. Geometric delta comparison conservatively retains full location/evidence and multiplicity, so an altered finding can be rejected even when its item IDs remain the same.

Footprint/track locks are checked in the Kernel and again by the IPC adapter because the native API can move locked items. The adapter acquires an advisory writer lease for this scratch project. Manual GUI edits are not atomically excluded; use an isolated single-writer session and fresh queries.

## Checkpoint and durable evidence

Named checkpoints include the normally saved PCB, schematic, project settings, custom rules, library tables/assets and a hash manifest. Native restore validates origin, artifact membership, all bytes and current state before copying/reverting, then verifies the full revision. It refuses observed external settings/board changes and attempts a recovery copy. It is not a general atomic multi-writer restore mechanism.

Journal sessions bind to the exact backend/project identity and terminal revision. An unfinished attempt, foreign journal, missing accepted state or failed completion evidence blocks writes with `RECOVERY_REQUIRED`. Checkpoint creation and restore evidence failures also latch recovery. Accepted native actions are saved before their terminal record; resume replays only a result matching current board state.

Moving a project does not authorize rewriting old checkpoint/journal identities. Old run artifacts are historical evidence; create a new run at the new location. No automatic uncertain-mutation retry or recovery-clear API is provided in this slice.

## Scripted native acceptance

Open `runs/capability/live/board.kicad_pcb` in PCB Editor and enable the local KiCad API. Confirm the exact socket/document; `api.sock` can belong to Manager while PCB Editor uses `api-<pid>.sock`.

```sh
.venv/bin/python experiments/kicad-ipc/probe_ipc.py --socket <confirmed-socket> --output runs/capability/<new-run>
.venv/bin/python experiments/kicad-ipc/kernel_smoke.py --socket <confirmed-socket> --output runs/kernel/<new-smoke>
.venv/bin/python experiments/kicad-ipc/kernel_conflict_smoke.py --socket <confirmed-socket> --output runs/kernel/<new-conflict>
```

The scripts select the exact scratch document. M1 smoke rejects a short and stale/locked writes, validates native flip/side/pad geometry, accepts explicit copper/via/zone actions, resumes the action journal without duplicate mutation and restores the baseline. Conflict smoke introduces a probe-owned saved-settings edit, proves restore preserves it and blocks the next write, then removes only its own unchanged bytes explicitly.

If any script stops with uncertain/conflicting state, inspect its JSON and preserve the scratch project. Do not rerun writes to guess whether they committed. Native smoke scripts may have changed the scratch board; a failed run is never a pass.

## Current acceptance status

See `docs/capabilities/m1-progress.md` for fresh evidence. Unit/native CLI regression runs are recorded separately from GUI-dependent native IPC acceptance. The initial M1 acceptance now passes on actual KiCad 10.0.6, including native smoke and settings conflict; see the ledger for exact evidence and the explicitly limited scope.

Beyond this slice: arbitrary board shapes, general manufacturing profiles, footprint-library/bootstrap/outline actions, multi-action transactions, broader geometry queries/scoped verification parity, export/release workflows, cross-platform recovery, host-driven autonomous routing acceptance, and OS-crash recovery across all delivery timings.
