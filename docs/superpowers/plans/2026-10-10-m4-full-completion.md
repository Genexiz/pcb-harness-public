# M4 full completion execution plan

> Use executing-plans inline for integration/ERC and dispatching-parallel-agents for three independent source, support and firmware domains; one final independent whole-change review after integration. User explicitly requests finishing the actual milestone, not stopping at another preparation substep.

**Goal:** Close all software/source/engineering work that can be completed now and produce the complete v2 target evidence, real circuit, firmware, layout/export only when upstream gates genuinely permit them.

**Spec:** PCB Harness — Design Spec (v2).md sections3/8/9/12 and Development Roadmap M4. Preserve targetSTM32F103C8T6/allnineinterfaces/64KB20KB, externalCAN, regulated5V, noautorouter/no paidservice/modelproviderkey.

**Architecture:** Parent owns integration and existing code. Three disjoint domains recover original sources, select/qualify exact support BOM and build actual full firmware. Every gate is tied to frozen sources/artifacts; manual/hardware evidence is never invented. Known ERC issues are fixed through source-reviewed semantic models and explicit power annotations, not exclusions.

### Task1: Source and exact hardware qualification
- [ ] Recover primary ST original bytes/revisions and MAX3232 exact package proof.
- [ ] Select exact per-reference support MPNs and package/pad/cap-bias/crystal/thermal/protection evidence.
- [ ] Integrate source-bound facts/assets/circuit revisions without altering old packets.

### Task2: Complete firmware and timing/capacity
- [ ] Build real nineinterface drivers/test firmware from pinned official source packages.
- [ ] Meaningful protocol/arbitration/queue tests, real ARMmap, staticstack/buffer budgets and bounded timing analysis.
- [ ] Integrate genuine firmware producer into M4 feasibility without claiming measured silicon behavior.

### Task3: Real circuit/ERC/native/prelayout closure
- [ ] Source-bind MCP2518FD SDO tri-state derivative; preserve original core assets.
- [ ] Explicit legitimate schematic supply-drive annotations; native ERC clean without ignored errors.
- [ ] Complete BOM/independent circuit review/M3bundle/native bootstrap/parity and full profile/mechanical/power/errata requirements.
- [ ] Assess genuine prelayout conditions. If user/hardware evidence is required, prepare exact concrete request with all autonomous work complete; never arbitrarily keep a hard-codedfalse flag or flip it totrue.

### Task4: Layout/release package where gates permit
- [ ] Agent-chosen floorplan/placement/routing under calibratednativeMCP, snapshots/checkpoints/scopedrepair; no autorouter.
- [ ] Save/refill/fullDRC/ERC/parity, export and geometry/BOM/placement consistency under exact profile.
- [ ] One independent full review, fixImportant/Critical with observedRED→GREEN, fullsuite and actual milestone report, localcommit.

## Exit
Finish the requested M4 outcome where evidence permits. Stop only at a real indispensable human/external dependency, after completing independent authorized work, and explain exact remaining requirement. Do not redefine task completion to a small producer slice.
