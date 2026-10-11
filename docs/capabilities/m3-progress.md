# M3 circuit grounding progress

Date: 2026-10-10

Implementation and native acceptance gate: PASS.

Retained post-review acceptance: `runs/circuit/m3-2026-10-10-final/report.json`; raw evidence is
local and ignored by Git. All four gates passed: strict bundle/independent
review/profile structure, native positive bootstrap, eight upstream circuit
negatives, and eight native fabrication negatives plus the clean baseline.
`integrity.json` binds every retained artifact, including reports, case inputs,
source snapshots, native project copies, command outcomes, netlist and SVG.
The earlier `runs/circuit/m3-2026-10-09` evidence remains preserved as the
pre-review result. It does not cover the seven findings fixed below.

## Proven behavior

- Eight offline versioned schemas reject duplicate JSON keys, nonfinite values,
  unsupported fields/versions, path escape and symlinked artifacts.
- Document hashes bind source facts and confirmation revisions. Part assets
  are checked against actual symbol pins and physical footprint pad numbers.
- Independent review rejects wrong pinout/footprint, missing interface,
  voltage mismatch, unresolved errata, duplicate ref, no-connect mismatch and
  concurrent native F103 USB/CAN use. External CAN is not treated as native CAN.
- Omitted required constraints remain detectable from the external checklist;
  critical unknown/manual facts remain explicit release blockers.
- Actual evaluator capability determines support. Unsupported quantities,
  missing thresholds or unknown evaluators remain blockers even when callers
  label their records confirmed or provide arbitrary evidence strings.
- Operating facts may carry an explicit two-number `range` in their declared
  units. Voltage bounds use `V`; a scalar nominal alone leaves operating-range
  evidence unknown. Declared pin ranges beyond sourced bounds are rejected.
- Logical pin ownership of pad numbers is unique; repeated physical pads with
  the same number remain supported for one logical pin. Recognized USB/CAN
  peripheral aliases are normalized; unknown native F103 assignments fail.
- Native compiled-rule negatives cover track width, copper clearance, via
  drill/diameter, annular ring, drill-to-inner-copper, hole spacing and copper
  to edge. Global minima are relaxed during these probes. The inner-copper
  probe uses four layers and separately relaxes copper clearance so the native
  checker reports the intended hole constraint. These are calibration inputs,
  not a blanket manufacturing-compliance assertion.
- Named-net conditions use `A.NetName`. Custom minima are ordered so the
  largest matching minimum wins, independently of input order. Live KiCad
  rejects 0.4mm tracks subject to a 0.8mm net constraint and accepts their
  compliant width under generic-first/generic-last/weaker-net-last inputs.
- Generated schematic/PCB has native clean ERC, geometric DRC and parity,
  exact exported netlist, caller-supplied bootstrap positions and no routing.
  Intentional no-connects have matching native net identity and exported
  `+no_connect` annotation. Native SVG source notes were visually inspected;
  an overlapping-note regression was fixed by line wrapping.
- Bootstrap requires every project/input/library/upstream artifact in its
  manifest and reruns circuit/profile/compilation checks before native CLI.
  Missing or failed reviews, semantic drift and symlinked native evidence
  directories are rejected before acceptance or external snapshot writes.

## Scope and remaining gates

`release_eligible` remains **false**. The fixture is synthetic; the real target
MPNs/packages/pin allocation, confirmed critical source facts, selected JLCPCB
service/stackup, assembly constraints and unsupported/manual fabrication
categories remain unresolved. The JLCPCB candidate profile has complete
category structure with unconfirmed data, not confirmed manufacturer minima.
No agent-created production human confirmation was added.

The writer currently supports single-sheet/unit unrotated symbols, audited
local assets, root-sheet named nets with Default class, rectangular outlines,
two/four layers and caller-declared positions. Native IPC rule acceptance was
not expanded. No model API key, inference provider or route search was added.

The final whole-change review identified seven Important findings, all fixed
with observed RED-to-GREEN regressions in one pass. Post-review full suite:
373 passing tests; native acceptance: all four gates true, 8/8 circuit and
8/8 fabrication negatives rejected, artifact integrity verified. Built wheel
imports circuit/fabrication capabilities and all eight offline schemas;
dependency and whitespace checks pass. Review details, rulings and two
deferred Minor findings are in [M3 final review](m3-review.md).
M4 real-target parts/resource/power/firmware feasibility is the next milestone;
full-board layout still requires those gates first.

## Reproduce

```sh
.venv/bin/python -m eval.circuit_smoke.run \
  --bundle fixtures/circuit/tiny \
  --checklist fixtures/circuit/tiny/checklist.json \
  --output runs/circuit/m3-new-repeat \
  --cli /Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
.venv/bin/python -m pytest -q
```

The output must not already exist. Missing/failed CLI verification closes the
native gate while preserving available circuit-negative results. The artifact
integrity check detects report/source/project drift; it is not a cryptographic
defense against a person rewriting both their own files and all stored hashes.
On this macOS host the native tests require execution outside the filesystem
sandbox: sandboxed PCB DRC exited `-6`, and boot-epoch reads were unavailable.
The unchanged 347-test baseline and the final suite passed outside that
sandbox. Those process failures were never treated as design passes.
