# Selected STM32 fabrication service — 2026-10-10

Selected engineering baseline: JLCPCB four-layer FR4, 1.6mm nominal, JLC04161H-7628, outer1oz/inner0.5oz, ENIG, green LPI, through vias, regular routed outline, top SMT plus manual THT. This is a concrete service choice for planning, not an order or approved manufacturing package.

Original manufacturer HTML snapshots are retained under `runs/m4/fabrication-source-2026-10-10`; hashes and canonical URLs are in `benchmarks/stm32-communications/fabrication-selected/sources.json`. Numeric limits and independently chosen margins cover all17 profile categories. Stackup dielectric/copper values are in `stackup.json`; they are nominal reference values, with thickness/impedance tolerances retained. No publisher copyright/license is transferred by retrieval.

The [rigid capability table](https://jlcpcb.com/capabilities/pcb-capabilities) and [stackup table](https://jlcpcb.com/impedance) support the selected service. The [assembly spacing matrix](https://jlcpcb.com/help/article/minimum-spacing-for-smd-components), updated2026-09-09, makes the1.50mm global non-BGA body spacing an explicit engineering margin. Package-specific measurement and the board geometry must still be checked; courtyard clearance alone is not that measurement.

`fabrication.json` and `facts.json` pass their offline schemas. `review_profile` reports complete category coverage and no internal issues, but release eligibility is false: every source fact is unconfirmed, and mask/silk/slot/assembly/lead-fit checks are retained as manual obligations. Native rules cover the supported categories only. No unknown is normalized to a passed production check.

Additional board obligations: separate via/PTH drill-to-inner-copper clearances, NPTH sealing/copper clearance, USB90ohm differential geometry under the selected stackup, connector lead/drill fit, thermal-pad stencil/paste, power-track widths, assembly rails/fiducials, module body/socket/height and plated-slot geometry. These are not silently collapsed into the17 scalar profile values. The saved board, exact BOM/CPL, Gerber/drill exports and manufacturing review must match this service before release.
