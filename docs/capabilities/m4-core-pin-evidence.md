# M4 core pin evidence

Date: 2026-10-10. Continuation of the approved exact-core preparation, under
`docs/superpowers/plans/2026-10-10-m4-core-pin-evidence.md`.

`core-pin-observations.json` records an independently transcribed manufacturer
number/name inventory and explicit saved-symbol aliases for all six core IC
types. The runner preserves the existing prepared assets and freezes their
complete integrity-checked preparation, observations, source lock and available
original PDFs before producing candidate evidence. No installed library or
editor document is changed.

| Candidate | Observation | Original source binding |
| --- | --- | --- |
| STM32F103C8T6 | 48 numbered aliases, LQFP48 | Unavailable; no original hash/facts emitted |
| MCP2518FD-E/SL | 14 pins; SL/SOIC14; explicit active-low aliases | DS20006027B Table1-1 p4; pp86-88/95 |
| MCP2562FD-E/SN | 8 pins; SN/SOIC8; pin5 VIO | DS20005284A Table1-2 p4; pp24-25/29 |
| THVD1450DR | 8 pins; D/SOIC8; R/RO and D/DI aliases | SLLSEY3E p5; PDF pp32/41-43 |
| MAX3232IDR | 16 pins; D/SOIC16 family; DIN/DOUT versus T aliases | SLLS410O pp1/3; exact orderable/land-pattern gap remains |
| TPS62162DSGR | 8 leads plus EP9; DSG/WSON; EP must connect to AGND | SLVSAM2E p4; PDF pp30/39-41 |

The five retained originals match the previously recorded hashes. PDF page
rendering and table inspection checked the relevant names, package columns
and exposed-pad distinction. The converter compares every explicit numbered
alias to the actual prepared symbol and preserves pad ownership from the
verified preparation. It does not derive manufacturer meaning from a PDF,
approve electrical pin types, validate alternate functions, or qualify a land
pattern. Manufacturer observations remain authored inputs for review.

The actual retained run `runs/m4/core-pin-evidence-final-2026-10-10` contains
`pin-comparison.json`, ten strict M3 identity facts in `facts.json`, the frozen
inputs/original PDFs, `report.json` and `integrity.json`. Five IC types and
55 numbered contacts have source-bound candidate observations; the MCU's
48 aliases have only an unbound web observation. Every fact is critical,
unconfirmed and has `confirmation=null`; `accepted_real_target_assets=0`.
The packet is not a complete M3 circuit bundle, and existing parts' required
identity fact IDs remain unresolved until valid confirmation. It deliberately
contains no invented STM32 original-file digest or operating voltage bounds.

The ST download was retried on the canonical publisher endpoint. The sandbox
could not resolve ST; outside the sandbox HTTP2 returned INTERNAL_ERROR and
HTTP1.1 timed out after25s with zero bytes. Web access to DS5319 Rev20 is useful
inspection but cannot supply an original-byte SHA-256. The original ST source
lock remains unchanged; RM0008 and ES096 are still unavailable too.

The retained MAX3232 datasheet's current ordering addendum does not contain an
exact MAX3232IDR row, and its mechanical appendix does not include the narrow
D/SOIC drawing. Family pin/body information supports a candidate observation,
not exact orderable/lifecycle or footprint qualification. No alternative MPN
is silently substituted. Obtain exact manufacturer orderable/package evidence
before purchasing or accepting this part.

## Reproduction

```sh
.venv/bin/python -m pcb_harness.orchestration.core_pin_evidence \
  --core runs/m4/core-assets-final-2026-10-10 \
  --source-root runs/m4/engineering-final-2026-10-10/sources \
  --output runs/m4/core-pin-evidence-new
```

Use a new output path. CLI exit2 is intentional: pin/package confirmation,
source integrity, library redistribution, WIZ550io, support BOM, firmware,
power/thermal, circuit native acceptance, mechanics, errata and fabrication
remain named prerequisites. `layout_allowed`, `release_eligible` and
`milestone_complete` remain false.

`verify_pin_evidence(root)` checks required artifact hashes and reconstructs
facts, comparisons and the entire report from frozen inputs plus the verified
core preparation. Changing a derived claim, accepted count, confirmation or
blocker and updating only its hash cannot manufacture a passing report.
This detects local evidence drift; coordinated rewriting of authored inputs
and all their digests is not cryptographic authentication of publisher claims.
The source envelope check is not a full PDF parser or semantic validation.

## Scope rulings

- Preserve the established non-main checkout and inline method; the authorized
  continuation covers reversible local evidence work. Cost if misunderstood:
  this local packet needs revision.
- Explicit aliases retain original symbol geometry and make manufacturer
  names reviewable. Cost if a transcription is wrong: an incorrect critical
  candidate observation, blocked from confirmation/layout until review.
- Keep source binding distinct from exact-orderable/package and land-pattern
  approval, especially MAX3232 and EP9. Cost if mistaken: wrong procurement,
  grounding, assembly or thermal design.
- Keep missing ST originals and all complete-board gates open. Cost if mistaken:
  insufficient evidence could be treated as a working STM32 board.

## Verification and independent review

Initial tests observed26 RED failures because the producer did not exist.
Synthetic cases exercise admission/binding and explicitly claim no manufacturer
truth. They cover missing/duplicate inventories and pins, wrong symbol aliases,
package/source identity, malformed/changed/missing/symlinked source bytes,
unavailable hashes, input overlap, original edits during capture and derivative
tampering even with refreshed hashes. The final packet preserves regulator
EP9's four copper shapes and keeps its stencil apertures outside pin ownership.

One independent read-only review found one Important retrieval-provenance gap,
no Critical or Minor findings. The reviewer checked all five original pin
tables/package locators and the retained packet, including EP9 and MAX3232's
explicit limits. `retrieved_url` had not been checked because it was absent
from the source specification's mandatory fields. Two missing/mismatched URL
tests failed before the fix and pass after requiring the exact calibrated
publisher URL. A third observed RED-to-GREEN test rejects numeric0 masquerading
as `human_confirmed=false` in source metadata. Future legitimate publisher
redirects need reviewed metadata; they are not silently admitted.

The single fix pass is complete; no second review was dispatched. Targeted
preparation/packet suite:70 passed. Final full suite outside the sandbox:
**561 passed in71.64s**, no skips. Wheel build, dependency and whitespace checks
pass. The final packet and original preparation both pass fresh verification.
The real runner returns2 with five sourced types/55 numbered contacts/ten
unconfirmed facts and all scope gates unchanged. This completes this evidence
continuation; full M4 and the complete STM32 circuit remain open.
