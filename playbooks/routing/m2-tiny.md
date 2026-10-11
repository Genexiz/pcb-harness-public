# M2 tiny-board host playbook

This is the frozen procedure for each of the five M2 routing-feasibility runs. It describes evidence and safety behavior only. It does not provide route coordinates, a preferred topology, layer choices, via locations, or an autorouting algorithm.

## Fixed experiment boundary

- Use one fresh `runs/routing/m2-2026-10-09/run-N/project/board.kicad_pcb` project and that run's new `service/` directory.
- The local server owns no model key. The Codex desktop subscription host chooses every placement, track path, layer, width, and via.
- Keep the launch envelope at exactly 300 admitted writes and 1200 seconds. Rejected, replayed, and rolled-back write requests consume attempts.
- Use only explicit PCB Harness MCP operations. Do not invoke KiCad's interactive router, an autorouter, a shove router, or a script that calculates route geometry.
- Use `strict` mode for every geometry action.
- Never automatically retry an uncertain, disconnected, or recovery-required write. Stop that run with its evidence intact.
- Do not close, restore, or discard unrelated KiCad documents.

## Per-run procedure

1. Call `pcb_status`, then `pcb_connect`. Confirm the fixed project path names the current run, backend is native KiCad, `native_editing_enabled` is true, recovery is false, the run budget is 300/1200, and no attempts were previously admitted.
2. Call `pcb_summary` and `pcb_verify_geometry` for the initial state.
3. Call `pcb_get_footprint` for `R1`, `R2`, and `R3`.
4. Call `pcb_net_info` for `/NET_A` and `/NET_B`.
5. Call `pcb_render_board` for a native whole-board view. Structured coordinates remain authoritative; the image is supporting context.
6. Call `pcb_create_checkpoint` with name `baseline` and the latest revision.
7. Choose and submit at least one placement-family action (`place_footprint`, `move_footprint`, `rotate_footprint`, or `flip_footprint`). The host supplies the complete action arguments.
8. After every admitted write, query `pcb_summary` or the changed footprint/net to obtain a fresh revision before the next write. Never reuse a stale revision.
9. Choose explicit `route_track` actions, and `add_via` only if the host judges it necessary. The host supplies every point, layer, width, via location, drill, diameter, and layer span. Query current net information and revision between writes.
10. Rejected or rolled-back actions stay in the transcript. The host may choose a different new action only after reading the safe result and fresh state; it must not resend an uncertain intent.
11. Finish with `pcb_verify_geometry`, `pcb_list_unrouted`, `pcb_summary`, and `pcb_render_board` after the last write.
12. Preserve the final project, host transcript, run-envelope ledger, checkpoint/verification artifacts, and any failure. Do not restore the baseline after a normal completed run.

## Pass interpretation

The scorer, not the host narrative, decides the run result. A passing run needs the exact native KiCad 10.0.6 backend, immutable input hashes, at least one accepted host-specified placement action, at least one accepted host-specified route action, complete durable write evidence, elapsed time within 1200 seconds, at most 300 attempts, clean mandatory geometric DRC, zero unconnected items, and clean schematic parity. This remains a routing-feasibility result, not fabrication release.
