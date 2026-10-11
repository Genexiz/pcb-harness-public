# KiCad 10 macOS — M0 capability report

Date: 2026-10-03 · Status: **M0 core capability gate verified**. Extended production recovery guarantees remain unverified.

## Environment and scope

- KiCad CLI: `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`, version `10.0.0`.
- Python: project-local 3.11 venv; `kicad-python==0.8.0`, pytest 9.1.1. Dependencies pinned in `requirements-m0.lock`; install this repository with `pip install -e . --no-build-isolation` for shared helpers.
- Binding API reports `10.0.6-0-gcaf7377e9c`. A successful `check_version()` does not prove each method is available.
- Development branch: `work/m0-kicad-capability`; no remote created.
- Immutable regression fixture: `fixtures/capability/`. Native editing only uses `runs/capability/live/board.kicad_pcb`, selected by exact resolved document/project path. Existing user projects were not edited.
- The fixture has three synthetic resistors, two nets, eight tracks and three through vias. Its footprint is a geometric probe, not a production package. This is not the STM32 board or a fabrication release.
- KiCad API was initially disabled and enabled for the approved local IPC spike. IPC access and some native CLI commands require approved execution outside this Codex sandbox.

## Verified matrix

| Operation | Actual API / command | Result and evidence |
| --- | --- | --- |
| Instance/document identity | `get_open_documents`, exact resolved project/file match | Scratch selected; wrong/ambiguous documents rejected by tests. Manager socket responds but has no `GetOpenDocuments` handler. PCB Editor socket changes after restart. |
| Geometry/nets | `get_footprints`, `get_tracks`, `get_vias`, `get_nets` | Exact IDs, net names, pad positions, angles, widths and drills recorded in `ipc-run-6/baseline.json`. |
| Move/rotate footprint | `update_items` | R1 staged at [30,18], 90°; pads at [30,19]/[30,17]. Published commit at [25,20], 90° has pads [25,21]/[25,19]. |
| Create/remove footprint | clone definition, fresh child IDs, `create_items`/`remove_items` | Counts 3→4→3; restored. General loading/bootstrap from a library is unverified. |
| Exact copper | explicit `Track`/`Via`, create/update/delete | B.Cu track [21,25]→[25,27], width 0.4→0.5 mm; via diameter 0.6, drill 0.3 mm; native readback and removal verified. |
| Commit/drop/revert | `begin_commit`, `push_commit`, `drop_commit`, `revert` | Staged queries return old published state; drop restores geometry; push publishes; guarded saved-board revert restores baseline. |
| Native flip | `flip_items` | **Unsupported**: KiCad 10.0.0 returns no handler for `FlipItems`. No automatic emulation. |
| Native lock behavior | locked footprint + `update_items` | API moves locked R1 to [26,20] while `locked=true`; Harness must enforce locks before writing. |
| Zone create/fill | `Zone`, `refill_zones(block=False)`, bounded ping | B.Cu zone filled; filled polygons returned; baseline restored. |
| External IPC writer | separate client publishes movement | Change observable; baseline restored in controlled single-writer probe. |
| GUI edit/stale guard | Properties GUI X=20→22 + IPC readback | Guard rejects stale restore; GUI undo returns baseline. `manual-reload/evidence.json`. |
| Save/reopen | normal save; quit/relaunch scratch PCB Editor | New instance socket, exact saved geometry and file SHA256 unchanged. `manual-reload/evidence.json`. |
| Lost mutation reply | send `EndCommit` once, close before receive | Durable uncertain record; independent readback observes committed X=24; no write retry; explicit guarded restoration. `lost-reply-1/report.json`. |
| Disconnected query | unreachable socket, 250 ms timeout | Connection error recorded; no write attempted. |
| DRC/parity | `pcb drc --format json --severity-all --schematic-parity --exit-code-violations` | Good fixture clean; short/clearance/width/open/net mismatch negatives rejected. Restored live board clean. |
| ERC | `sch erc --format json --severity-all --exit-code-violations` | Good schematic clean; conflicting output pins detected across sheet reports. |
| Custom width rule | `.kicad_dru`, explicit `min 0.2mm` | Independently rejects 0.10 mm track with global floor lowered to 0.01 mm. Unknown/malformed/unitless rule text blocked before CLI. |
| SVG/layers/crop | native multi-layer SVG; `probe_render.py` | Six pad centers, eight F/B copper endpoints and outline match IPC; explicit R1 SVG crop. Wrong pad geometry rejected. |
| Verification failure paths | fail-closed report reader | Missing/unknown schemas, source mismatch, omitted sections/severities, process failure, stale PASS and disabled essential checks block pass. |
| Full project restore | experimental M1 implementation/smoke | Separate milestone evidence exists; not included in this M0 guarantee. Native PCB `revert` alone does not restore every project setting. |

## Native contracts and findings

1. On this macOS sandbox, parity CLI can abort during application registration (`_RegisterApplication`/wx UI initialization). The same command succeeds outside sandbox. Ordinary DRC can also require UI initialization on some violation paths. A crash or absent report is a tool error, never a clean board result.
2. `api.sock` must not be assumed to be PCB Editor. During continuation it belonged to KiCad Manager; the scratch editor used `api-74261.sock`, then `api-74371.sock` after restart. Probe the exact document before any mutation, and rebind after restart. Successful version queries alone are insufficient.
3. A commit stages updates, but queries return published geometry until `push_commit`. Update/create responses contain staged items. Post-publish verification plus guarded recovery is necessary; pre-publish queries cannot validate the staged board.
4. Save destinations must be absolute. Native `save_as` resolves relative paths under the board project directory, not Python cwd. Normal save and SaveCopy/GetString serializers can differ in formatting/metadata; inverse geometry edits do not guarantee an identical full revision.
5. The pinned binding's blocking refill loop does not increment its timeout counter. Probes use nonblocking fill and a tested monotonic deadline; unresolved completion stays uncertain.
6. ERC JSON stores violations under `sheets[*].violations`. Canonical local net labels are `/NET_A` and `/NET_B`; parity also checks component fields such as Description.
7. An early ERC coordinate diagnostic reported unexpectedly scaled values. ERC coordinates are not calibrated for precision input; IPC remains geometry authority. Fontconfig warnings are preserved; global font configuration was not changed.
8. Unitless custom thresholds did not enforce the intended 0.2 mm width. Malformed rule text could be silently ignored by native CLI with zero violations. Only the exact audited M0 rule subset is accepted. General factory/board-dependent rules and coverage auditing remain M3 work.
9. The report parser audits the fixture's explicit default ignored-check allowlist and rejects extra/unknown disabled checks. Allowed ignored checks are retained in reports. A clean result is still limited to the active, audited checks; production profiles must define required coverage.
10. Revert guards inspect full serialized PCB and related saved project/rule/library hashes. These checks are not atomic compare-and-swap: a concurrent writer can race readback and unsaved settings can be invisible. Mutation probes require an isolated single writer. Unexpected state must be preserved, not overwritten.

## Render calibration

The observed combined SVG has dimensions approximately 60.0456 × 20.0406 mm for the 60 × 20 mm outline. One SVG unit is one mm; x increases right and y down. For this fixture/export only:

`svg_xy = board_xy + [-9.975, -9.975] mm`

The R1 crop covers board coordinates [16,17]–[24,23] mm with SVG viewBox [6.025,7.025,8,6]. It retains the native scene and uses the viewBox as a Harness crop. Native F.Cu/B.Cu/Edge.Cuts colors were checked, including per-path style overrides inside groups. No net highlighting or ruler is claimed as a native API capability.

Arbitrary outlines, rotated export modes, other versions, raster pixel mapping and graphical net overlays remain unverified. Calibration must fail closed when the observed SVG shape/transform disagrees with IPC.

## Evidence and repeatability

Paths below are relative to `runs/capability/`; generated runs are ignored by Git, while fixture/probe/test sources are committed.

- `preflight/`: executable version/help/dependencies/input hashes.
- `ipc-run-6/report.json`: nine supported operations, one unsupported flip; `baseline_restored=true`.
- `manual-reload/evidence.json`: GUI edit readback/stale rejection/undo and new-instance reload geometry/file hash.
- `lost-reply-1/report.json`: intentionally retained uncertain operation; published commit observed, zero write retries, baseline restored. This controlled socket fault is not an OS/process-crash or every delivery-timing proof.
- `cli-continuation/{summary,drc,erc}.json`, `board.svg`: immutable fixture DRC/parity PASS, ERC PASS, render PASS.
- `live-final/{summary,drc,erc}.json`: final edited/reloaded/restored live fixture DRC/parity and ERC PASS.
- `render-calibration-2/report.json`, `r1-crop.svg`: calibrated native geometry/layers/crop. `render-calibration-negative/result.json`: wrong IPC pad position rejected without a PASS report.
- `tests-m0-continuation.txt`: **47 passed** across real KiCad fixture tests (10) and report/probe safety tests (37).

M0 commands:

```sh
.venv/bin/python -m pytest tests/test_capability_fixtures.py tests/test_verification.py tests/test_probe_safety.py -q
.venv/bin/python experiments/kicad-ipc/verify_fixture.py --output runs/capability/<new-cli-run>
.venv/bin/python experiments/kicad-ipc/probe_ipc.py --socket <confirmed-PCB-editor-socket> --output runs/capability/<new-ipc-run>
.venv/bin/python experiments/kicad-ipc/probe_lost_reply.py --socket <confirmed-PCB-editor-socket> --output runs/capability/<new-fault-run>
.venv/bin/python experiments/kicad-ipc/probe_render.py --svg <native-SVG> --geometry <IPC-baseline.json> --output runs/capability/<new-render-run>
```

Fresh M0 review previously found four Important issues: unguarded revert, stale PASS summary, non-durable uncertainty and unbounded zone polling. Fixes have RED→GREEN tests and the native continuation exercises guards and the lost-reply path. Native unsupported operations remain explicit.

## Remaining limits

The core M0 gate is achieved, with no API-key blocker. It does not prove arbitrary board/project checkpoint recovery, crash-at-every-delivery-phase recovery, atomic GUI concurrency, unsaved settings preservation, portable Linux/container support, footprint library bootstrap, or fabrication readiness. These are explicit backend constraints and later milestone checks, not reasons to silently relax verification.

The user's Google API key is not yet available. This affects real Gemini evaluation at M2; M0 requires no model provider.

## References

- [KiCad IPC add-on documentation](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/)
- [Official kicad-python package](https://pypi.org/project/kicad-python/)
- [KiCad 10 CLI reference](https://docs.kicad.org/10.0/en/cli/cli.html)

Runtime contracts were inspected in the installed 0.8.0 binding and tested against the installed native 10.0.0 executable; documentation links do not establish method availability.


## KiCad 10.0.6 continuation (2026-10-09)

The original matrix above records 10.0.0. Current 10.0.6 native probes now verify all ten operations including native flip; `runs/capability/kicad-10.0.6-ipc-reviewed-2026-10-09/report.json` has baseline_restored=true. Current M1 native smoke and saved-settings conflict pass with exact baseline restoration; see docs/capabilities/m1-progress.md.

FlipItems is immediately visible to queries before push on 10.0.6; this differs from ordinary staged UpdateItems. The initial probe stopped because it assumed staged visibility, then its full-text guard detected regenerated R1 property UUIDs after drop. Full parsed-state comparison confirmed only the four R1 property UUIDs changed; explicit exact-state/hash guarded revert restored the complete semantic baseline and saved bytes. Failed and reconciliation artifacts remain under runs/capability/kicad-10.0.6-ipc-2026-10-09. The successful probe records visibility instead of assuming it and still requires post-push side/pad readback plus guarded revert.

MCP writes are accepted only for a connected native instance on exactly 10.0.6. Future patches/majors need separate acceptance even if the primitive adapter advertises flip capability. These probes do not prove arbitrary geometry/factory rules or all OS-crash recovery timings.
