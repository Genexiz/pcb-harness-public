# M2 routing feasibility progress

Date: 2026-10-09

Gate: PASS

The frozen five-run campaign at `runs/routing/m2-2026-10-09-r3/` passed 4/5 runs. The required threshold is at least 3/5. Raw campaign evidence is local and ignored by Git; `report.json`, every `score.json`, host transcript, run-envelope ledger, native checkpoint/DRC artifacts, final project copy, and final render remain under that directory.

## Scope and host disclosure

- Host: Codex desktop subscription.
- Exact model revision: unavailable.
- Sampling settings: unavailable.
- Provider tokens: unavailable.
- Provider cost: unavailable.
- Model-provider API key used by Harness: false.
- Backend: exact native stable KiCad 10.0.6 through the local MCP server.
- This is host-driven feasibility, not a controlled provider comparison and not fabrication release.

The tracked playbook is `playbooks/routing/m2-tiny.md`. It contains safety/query order and pass criteria, but no route coordinates, layer choices, via positions, route search, or golden topology. The host selected one placement action and four explicit `route_track` actions in every passing run. No autorouter or interactive router was used.

## Scored campaign

| Run | Result | Attempts | Elapsed seconds | Placement actions | Route actions | Final native result |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `run-1` | PASS | 6 | 234.744 | 1 | 4 | geometric DRC clean; zero unconnected; parity clean |
| `run-2` | PASS | 6 | 240.979 | 1 | 4 | geometric DRC clean; zero unconnected; parity clean |
| `run-3` | PASS | 6 | 236.879 | 1 | 4 | geometric DRC clean; zero unconnected; parity clean |
| `run-4` | PASS | 6 | 232.850 | 1 | 4 | geometric DRC clean; zero unconnected; parity clean |
| `run-5` | FAIL | 1 | 3.011 | 0 | 0 | checkpoint reply timed out; `RECOVERY_REQUIRED`; no retry; final state unverified |

All passing runs remained far below the frozen 300-action/1200-second envelope. The aggregate report retains the run-5 failure code and marks mandatory DRC, zero-unconnected, and parity criteria false because no post-write verification exists.

Final saved-file recheck on 2026-10-09 ran native `kicad-cli pcb drc --format json --severity-all --schematic-parity --exit-code-violations` against runs 1–4. All four returned exit code 0 with zero violations, zero unconnected items, and zero parity issues; reports are retained as `final-recheck-run-{1..4}.json` in the campaign directory. Regenerating the aggregate score afterward preserved Gate PASS 4/5.

The final independent code review found five evidence-validation gaps. Regression tests now cover final project/snapshot drift and native execution results, transcript/ledger contradictions, incomplete clock evidence, reused relay paths, and incomplete campaign reporting. The corrected scorer still reports 4/5 from the retained native campaign.

## Environment and failure evidence retained

The first native `save_as` verification after opening each fresh project changes KiCad's serialized live state. To avoid binding a checkpoint to a moving baseline, runs in the scored campaign used a separate retained read-only stabilization service: the first verification records `CONCURRENT_EDIT`, the second verifies the settled unrouted project, and only then does the scored service start with zero admitted writes. This setup dependency is a real tool-ergonomics limitation.

Earlier preparation is preserved locally:

- `runs/routing/m2-2026-10-09/`: initial fixture name was rejected by the deliberately exact M0 rule validator before any board write. The tracked fixture was corrected back to the native-accepted rule text with the same explicit `0.2mm` constraint.
- `runs/routing/m2-2026-10-09-r2/`: retained environment attempts include checkpoint capture failing after an unstabilized document, a stale PCB Editor socket after `pcbnew` exited, and a locked-Mac/busy interval. These attempts motivated the explicit read-only stabilization boundary; they were not rewritten into passing runs.

No failed or uncertain board write was automatically retried. The scored campaign is `r3`; earlier directories are diagnostic preparation evidence and are not counted as extra successful repeats.

## Decision

M2 single-agent placement/routing feasibility passes for this tiny reviewed circuit: 4/5 scored native runs satisfy mandatory DRC, zero unconnected items, circuit parity, and the frozen budget. The failure demonstrates the intended safety boundary: a lost checkpoint reply stops the run instead of guessing or retrying.

This result does not prove arbitrary-board routing, fabrication readiness, multi-agent benefit, model-to-model superiority, or the STM32 communications board. M3 requirements/parts/circuit/rules is the next milestone; the first-save stabilization ergonomics should remain visible rather than hidden in future benchmark setup.
