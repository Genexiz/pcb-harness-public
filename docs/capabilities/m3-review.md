# M3 final review and decision

Date: 2026-10-10. Implementation range reviewed: `02c9db0..2eff5f9`;
approved plan: `docs/superpowers/plans/2026-10-09-m3-circuit-grounding.md`.
The original single reviewer stopped at an account usage limit before its
verdict. This continuation recovered its findings and finished the outstanding
review. There was one implementation fix pass and no post-fix re-review.

## Important findings and verification

| Finding | Result and regression evidence |
| --- | --- |
| Named-net conditions and rule precedence | Use `A.NetName`, then order dimensional minima so the largest matching rule wins. Three real KiCad cases reject 0.4mm at a required 0.8mm and accept compliant width, independently of rule input order. |
| Missing or failed upstream bootstrap evidence | Require project/settings/rules/input/library/report hashes; rerun upstream circuit/profile/compilation and compare semantic inputs and emitted settings/rules. Seven omission cases and two failed-report cases reject before CLI. |
| F103 native peripheral spelling | Canonical USB/CAN aliases trigger the same conflict; unknown native identities fail. Explicit external CAN remains accepted in the synthetic fixture. |
| Aliased logical pad ownership | Every pad number has one logical owner; repeated physical pads with that number remain supported. Both shared-pad and repeated-map regressions reject. |
| Unsupported evaluator evidence | Circuit review, fabrication review and compilation use one actual capability map. Unsupported quantity/evaluator or null threshold remains unknown; nine unsupported fabrication categories remain release blockers even if labeled rule/confirmed. |
| Symlinked native evidence output | Resolve the native evidence path before directory creation or copying. The regression leaves the external target directory empty. |
| Unbound operating voltage ranges | Optional numeric fact `range` supplies explicit bounds in `V`. A scalar nominal leaves bounds unknown; declared ranges beyond sourced bounds fail; exact sourced ranges are auditable. |

All seven findings were graded Important by their effect on circuit acceptance
or local evidence containment. There were no Critical findings. The first
17 regression cases and the additional 9 cases failed against their respective
pre-fix behavior; focused runs passed after the fixes. The full post-review
suite passed 373 tests. KiCad version remains exact stable `10.0.6`.
The named-net property and reverse custom-rule evaluation order were also
checked against the [official KiCad 10 rule documentation](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html#custom-design-rules);
the native regressions establish that this compiler enforces those rules.

Post-review retained evidence: `runs/circuit/m3-2026-10-10-final`.
All four acceptance gates passed, both eight-case negative sets were rejected,
and artifact integrity verified. `release_eligible=false`. The wheel resolves
the eight packaged schemas and shared evaluator module offline.

The prior unmodified baseline passed 347 tests outside the sandbox. Inside
the sandbox it had 20 failures: 18 native KiCad DRC process failures with exit
`-6` and two unavailable boot-epoch checks. Native verification was rerun
outside the sandbox; none of these process failures was counted as a circuit
pass. The original review's bootstrap adapter probes were subsequently
confirmed with live native KiCad in this continuation.

## Rulings and practical costs

- Isolate native fabrication probes from redundant circuit-width rules and
  unrelated copper-clearance violations; use four layers for the inner-copper
  probe. Cost: calibration applies to the recorded isolated configurations,
  not blanket manufacturer compliance.
- Scope new projects to `runs/` under the nearest input workspace
  `pyproject.toml`, or the copied input parent for standalone bundles; preserve
  the fixture's recorded 10mm outline origin. Cost: standalone input/output
  must share the workspace parent.
- Keep calibration mutations in `eval/circuit_smoke/cases.py` and bind retained
  artifacts with integrity hashes. Cost: an extra evaluation module/manifest;
  unsigned hashes do not authenticate a person rewriting all evidence.
- Centralize native evaluator support in `fabrication/capabilities.py`. Cost:
  one shared capability module; reviews cannot independently claim support
  that the compiler lacks.
- Add optional fact `range` rather than interpret free-text or a scalar as
  both voltage bounds. Cost: operating facts without sourced bounds remain
  unknown for release. No production human confirmation was created.
- Keep full STM32 BOM/resource/firmware/power/thermal feasibility in M4. Cost:
  no actual-board readiness can be inferred from M3 calibration.
- Keep manufacturing confirmation and hardware performance in release/M5.
  Cost: software passes do not authorize fabrication or hardware claims.
- Require complete artifacts and semantic checks without treating rewritten
  local hash manifests as cryptographic proof. Cost: external signatures or
  authority would be required for authenticity against wholesale rewriting.
- Keep custom-rule IPC integration outside M3 and preserve its existing exact
  scratch-backend guard. Cost: new compiled rules are validated by saved-file
  CLI, not arbitrary live-editor writes.
- Preserve the authorized local branch, plan ledger and native evidence.
  Cost: ignored evidence remains on disk for inspection; no merge or push.

## Deferred Minor findings

- Malformed asset trees can raise indexing errors instead of a structured
  `ASSET_MISMATCH` response.
- Conflicting library assets can be detected after some fresh project files
  are written. The output is rejected/incomplete and never accepted.

Decision: M3 software/native calibration complete after these fixes. Actual
board release eligibility remains closed; M4 feasibility is the next gate.
