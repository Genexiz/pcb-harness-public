# M3 grounding and bootstrap playbook

1. Load all eight input documents through the strict offline bundle loader.
   Freeze hashes, independent checklist revision and exact native CLI version.
2. Audit cached document bytes, fact/source/confirmation binding, MPN/package,
   local symbol/footprint hashes, actual symbol pins and physical pad mappings.
   Treat synthetic or unconfirmed critical facts as release blockers.
3. Run independent circuit review against the explicit separate checklist.
   Check functions, interface count/role/rate/concurrency, pin allocation,
   voltage compatibility, errata, intentional no-connect and coverage from
   required facts/constraints. Failed review stops project writing.
4. Review every fabrication category for the selected service/stackup. Compile
   only supported explicit-unit rules. Keep unsupported/manual/unknown entries
   visible. Engineering targets are not manufacturer minima.
5. Write a fresh project under the input workspace's `runs/`. Use caller-supplied
   schematic and bootstrap positions; create no segments, vias or zones.
   Never overwrite an existing project or change a user's live editor document.
6. Verify a hash-bound saved copy through exact KiCad 10.0.6 ERC, full DRC with
   parity, XML netlist and SVG export. Compare native endpoints independently,
   including explicitly approved single-pin `+no_connect` nets. Expected
   unrouted connectivity is separate from geometry/ERC/parity acceptance.
7. Inspect the native schematic SVG for refs, values, labels, blocks and source
   notes. Preserve failures and all raw command/report evidence.
8. Run deterministic acceptance and report each gate separately. Verify the
   artifact integrity manifest before quoting a retained acceptance result.

Current writer scope: single sheet/unit, unrotated symbols, authored local
assets, root-sheet named nets with Default class, two/four copper layers,
rectangular outline with recorded 10mm origin, explicit bootstrap positions.
Unsupported forms are capability errors; this is not a general schematic
layout engine or a replacement for real-part/human circuit review.

M3 acceptance uses the tiny synthetic calibration circuit. A software gate
pass does not freeze the real STM32 BOM, confirm JLCPCB service suitability,
prove firmware/resource/thermal fit, or establish routed/release/hardware status.
The unchanged M0 native IPC guard still accepts only its tested scratch rules.
