# M4 exact core asset preparation

Date: 2026-10-10. Plan: `docs/superpowers/plans/2026-10-10-m4-core-asset-preparation.md`.
The approved v2 target and established non-main checkout are preserved.

`pcb_harness.orchestration.core_assets` captures the candidate manifest,
design/source-link manifests and the observed symbol/footprint bytes before
preparing exact-MPN local assets. Source digests, pin names/types/numbers and
electrical pad shapes must match the earlier inspection. Declared templates,
packages, MPNs and grouped references must match the calibrated target.

The flattener copies the nearest inherited properties and original units,
renames unit prefixes and removes `extends`; it changes no electrical pin
geometry. Missing/cyclic parents, duplicate properties/symbols/pins, malformed
unit prefixes and ambiguous inherited geometry are rejected. A child with its
own geometry plus parent geometry is deliberately unsupported rather than
silently merged. This fits the inspected installed library ancestry.

The final real run is `runs/m4/core-assets-final-2026-10-10`. Its strict M3 `parts.json`
contains six standalone exact-MPN symbols and footprints:

| MPN | Instances | Symbol pins | Structural package |
| --- | --- | --- | --- |
| STM32F103C8T6 | U1 | 48 | LQFP48 |
| MCP2518FD-E/SL | U2/U3 | 14 each | SOIC14 |
| MCP2562FD-E/SN | U4/U5 | 8 each | SOIC8 |
| THVD1450DR | U6 | 8 | SOIC8 |
| MAX3232IDR | U7 | 16 | SOIC16 |
| TPS62162DSGR | U8 | 9 including EP | WSON8+EP |

The two CAN symbols use reviewed-as-geometry templates, not substitute MPNs.
Value, Footprint, Datasheet, Description and footprint-filter fields identify
the actual selected part. The regulator retains all four copper pad9 shapes
and its two stencil apertures. The RS485 asset explicitly uses the selected
SOIC8 package rather than the installed DR symbol's conflicting VSON default.
No installed libraries were modified.

`core-bom.json` expands all eight IC instance references and keeps M1 as the
ninth core instance with exact WIZ550io v1.2 identity and unavailable asset.
`support-requirements.json` lists twelve unresolved support categories across
power/clock/reset/debug, all nine interfaces, connectors/protection and
mechanics. This is a core inventory, not a complete purchase BOM.

Each part declares missing pinout/package fact IDs, with no invented voltage
limits or human confirmation. No complete circuit bundle or schematic was
claimed. `accepted_real_target_assets=0`, layout/release/M4 completion remain
false, and the CLI returns2. Structural preparation is useful input for the
following source-bound circuit stage; it is not electrical acceptance.

## Reproduction and evidence

```sh
.venv/bin/python -m pcb_harness.orchestration.core_assets \
  --library-root /Applications/KiCad/KiCad.app/Contents/SharedSupport \
  --output runs/m4/core-assets-new
```

Use a new output path. The library root is installation-specific and must
match the recorded original hashes. The output retains input bytes, exact
assets, parts/core-BOM/support reports, attribution notice and integrity
manifest. `verify_core_assets(root)` verifies required hashes, captured input
admission and per-part semantic agreement with the captured sources: full MPN,
package, document link, symbol properties/geometry, footprint shapes and every
instance BOM row. Tampered, inconsistent or missing evidence fails even if a
derived file's digest was updated. Report counts, prerequisite categories and
unconfirmed status must also agree with this producer's actual scope.
The mechanism detects local drift, not deliberate coordinated rewriting of
all owned evidence and its hashes.

The [KiCad library license](https://www.kicad.org/libraries/license/) is
CC-BY-SA4.0 with its design-output exception. Library collections, including
modified collections, have separate redistribution obligations. Prepared
assets and original library snapshots stay in ignored local run directories;
`NOTICE.md` records attribution, changes and license URLs. Full upstream
license documents/attribution review remain required before publishing a
collection. No project license was selected by this preparation step.

Tests cover synthetic inputs explicitly labeled as such, multi-level
inheritance, malformed inputs, exact target identity/package/ref admission,
hash/pin drift, capture during live-input edits, reused/symlinked paths,
required artifact removal and Boolean values masquerading as metadata numbers.
The Boolean cases were observed RED before the admission fix. Targeted
flatten/preparation/asset/writer tests:81 passed after review fixes.

## Independent review and fixes

Independent read-only review of `0306a33..cbef89c` found two Important issues,
no Critical or Minor findings. One fix pass addressed them; no re-review was
dispatched. The reviewer independently compared all six real generated symbols
to their complete source geometry and ran the then-current35 new tests.

1. Design package and source ID/link could disagree with the calibrated MPN.
   U1 could say BGA100 and link to the buck document while using LQFP48 geometry.
   Admission now checks exact package descriptions, document IDs and publisher
   URLs for every core part, including the unresolved module. Three observed
   RED-to-GREEN cases cover package, source ID and source URL substitution.
2. The verifier checked captured sources and generated assets separately.
   Swapping two MPN declarations while updating the derived file's digest could
   pass. It now reconstructs each deterministic derivative from captured
   sources and compares its full metadata, symbol properties/geometry,
   footprint geometry and instance BOM. Six observed RED-to-GREEN cases cover
   MPN/package/BOM and symbol Value/Datasheet/footprint shape inconsistencies.

Seven additional observed RED-to-GREEN cases cover overstated counts, omitted
prerequisites, falsely complete support BOM, Boolean report metadata and a
returned blocker-list mutation affecting verifier rules. The latter now returns
an independent list; published evidence verification remains stable.

KiCad10.0.6 opened and exported all six standalone symbols to SVG in
`runs/m4/core-assets-native-2026-10-10/svg`. This is format/geometry acceptance,
not an STM32 schematic/ERC/functional result. Native export first failed because
the CLI does not create missing parent directories; creating the parent and
rerunning succeeded. The seven final symbol-library/footprint files have the
same hashes as those opened by the native export. Wheel/dependency/diff checks
pass. Final full suite outside the sandbox: **528 tests passed in66.73s**, no
skips. The final retained run passes hash and semantic verification, returns2,
and keeps all named prerequisite categories unresolved. No deferred Minor
findings; this preparation plan is complete, while full M4 remains open.

## Scope rulings

- Preserve the existing approved target and inline execution; cost if wrong:
  reversible local preparation or path calibration needs revision.
- Reject ambiguous inherited geometry instead of merging it; cost if wrong:
  another library family needs a separately reviewed extension.
- Keep manufacturer electrical/package facts and publisher-source failures
  unknown; cost if mistaken: an electrically wrong asset could enter a circuit.
- Keep WIZ550io/support BOM and full-board gates unresolved; cost if mistaken:
  omitted protection/connectors or a mechanically invalid design.
- Keep asset collection publication/license review open; cost if mistaken:
  incomplete attribution/license material could be redistributed.
- Retain broader inheritance families as unsupported and complete board
  approval as separate gates; cost if mistaken: a future library needs an
  extension, or a geometry result could be confused with a working circuit.
- Local drift/semantic checking does not authenticate coordinated rewritten
  input evidence; cost if mistaken: false trust in attacker-controlled inputs.
