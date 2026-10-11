# M4 engineering evidence review

Date: 2026-10-10. Review range: `2c13cca..bb675c4`. Independent read-only
reviewer under `executing-plans`; the previous attempt ended at a usage limit
without a verdict. This continuation closes the evidence-producer review,
not the full M4 board milestone.

Verdict: with fixes. Three Important findings, no Critical or Minor findings.
One fix pass reproduced all three with nine observed failing test cases;
the targeted M4 suite then passed all 96 tests. No second review was dispatched.
Final full suite outside the sandbox: **469 tests passed in 63.81 s**, no skips.
The sandbox-only run had 437 passing and 23 failing tests because native KiCad
CLI aborted with -6 and boot-epoch evidence was unavailable. The same pre-fix
suite outside the sandbox passed all 460 tests; no product workaround was
introduced for those environment restrictions. Final wheel build, dependency
check and `git diff --check` passed.

1. VDD could borrow the same part's VIO current fact, shrinking the 5 V reserve
   from 0.16 A to 0.002 A while claiming a documented full-load bound. Facts and
   loads now carry a structured `supply_domain`; both current and voltage
   applicability enforce the expected VDD/VIO identity. Four regressions cover
   substitutions in both directions for both kinds of fact.
2. Power coverage ignored U8 and unaccounted candidate devices. The calibrated
   inventory now requires the complete reference set, the TPS62162DSGR U8 and
   agreement with `design.power.regulator`. Four regressions cover a missing
   regulator, a replaced regulator, a replacement in both fields and added U9.
   Numerical current rating remains a design input, not source-bound proof of
   load, efficiency or thermal performance; power qualification stays unknown.
3. Source hashing and format inspection read different file versions. They
   now inspect one immutable byte buffer. Capture independently verifies both
   digest and envelope on the bytes actually written to the retained snapshot.
   A controlled invalid/valid/invalid publisher-file replacement previously
   passed audit and retained invalid PDF bytes; its regression now rejects it.

Fresh real cross-build: Flash 576 B; static data 9104 B; stack reservation
4096 B; total RAM 13200/20480 B. This is still an incomplete CRC/queue resource
probe. Final report: `runs/m4/engineering-final-2026-10-10/report.json`.
CLI exit 2; report integrity passed. CAN arithmetic remains 384/1280 B,
power reserves remain 0.572 A on 3V3 and 0.16 A directly on 5 V, and eight of
eleven publisher files are retained. Layout, release and M4 completion remain
false with the same seven prerequisite categories.

## Scope rulings and remaining evidence

- Ruling: preserve the established non-main checkout and approved inline v2
  target. Cost if wrong: local changes need revision or native-path calibration.
- Ruling: retain the WIZ550io 54/55 mm conflict and use 56 mm only for conservative
  screening. Cost if wrong: additional drawing review or physical allowance.
- Ruling: preserve 100 kHz I2C with the planned errata conditions. Cost if wrong:
  an explicit design revision or topology restriction is required.
- Final ruling: complete firmware, native ERC/parity, exact support BOM/assets,
  thermal qualification, connectors and fabrication remain prerequisites.
  Cost if treated as complete: capacity, electrical or manufacturing failures.
- Final ruling: actual silicon identity and implemented errata workarounds
  remain unknown. Cost if mistaken: missed I2C/USB device limitations.
- Final ruling: publisher semantics and the WIZ550io dimensional disagreement
  remain unconfirmed. Hash/envelope checks cannot resolve them. Cost if mistaken:
  incorrect electrical assumptions or physical fit.
- Final ruling: deliberate coordinated rewriting of artifacts and their owned
  hash manifest is outside this local drift detector. Cost if mistaken:
  false trust in attacker-controlled evidence; this is not an authenticity proof.

No deferred Minor findings. Source retrieval failures stay named; no ST hash
was invented. No native board mutation or manufacturing operation occurred.
