# M4 core asset inspection

Date: 2026-10-10. KiCad CLI reports 10.0.6 on this installation. This is the
next prerequisite after engineering review, under the approved v2 target.
No new MCU/interface choices or user action are needed to continue it.

`benchmarks/stm32-communications/core-asset-candidates.json` records six IC
template candidates, observed library/footprint SHA-256 values, inheritance,
actual symbol pins and electrical pad numbers. The metadata does not bundle
or license the installed library files. Recheck these hashes before producing
local assets; installation paths and generic/template symbols are not an
accepted portable part bundle.

| Candidate | Installed observation | Required next work |
| --- | --- | --- |
| STM32F103C8T6 | STM32F103C8Tx inherits 48 pins; LQFP48 numbers match | Flatten explicitly and review retained ST/package evidence |
| MCP2518FD-E/SL x2 | Exact SOIC symbol absent; MCP2518FD-xQBB is DFN with pad15 | Create the exact SOIC14 symbol; MCP2517FD-xSL is a geometry template only |
| MCP2562FD-E/SN x2 | Exact FD symbol absent; non-FD MCP2562-E-SN has eight matching numbers | Create the exact FD symbol and review each pin; do not substitute the non-FD MPN |
| THVD1450DR | The installed DR symbol explicitly selects VSON; THVD1450D selects SOIC8 | Use a reviewed local exact-MPN asset with SOIC8; reject the DR library default |
| MAX3232IDR | Generic MAX3232 inherits MAX232 and has no default footprint | Explicitly select/review SOIC16 and the exact part mapping |
| TPS62162DSGR | Inherited symbol has pins1-9; WSON has repeated copper pad9 and two unnumbered stencil shapes | Flatten exact identity; keep all pad9 shapes; review EP and layout requirements |
| WIZ550io v1.2 | No module symbol found in installed libraries | Create a revision-specific symbol/footprint after resolving header/mechanical evidence |

The [TI THVD1450 ordering addendum](https://www.ti.com/lit/ds/symlink/thvd1450.pdf)
identifies THVD1450DR as SOIC (D), eight pins; DRBR/DRBT are SON (DRB). This
confirms a local-library mismatch, not a requirement to change the selected
MPN. Generic symbol pin labels may differ from manufacturer labels; number-set
equality alone does not prove electrical pin identity or correct circuitry.

## Asset auditor and writer repair

The actual regulator footprint exposed a software gap: stencil apertures were
counted as logical electrical pads. The auditor now maps copper contacts and
excludes non-plated holes and paste-only shapes. Unnumbered copper is rejected,
and unknown numbered copper still requires ownership. Duplicate electrical
pads remain represented. The writer retains non-electrical shapes without
assigning nets or carrying stale pin/net annotations.

Five positive asset/writer cases failed before the fix and now pass; two copper
negatives continued to reject. Targeted asset/writer suite: 30 passing tests.
The final full suite outside the sandbox passed **477 tests in 64.67 s**, no
skips, including the reviewer-requested duplicate-copper case. All six recorded
library and footprint hashes were rechecked against the live installation.
Wheel build and whitespace checks passed.

Saved-copy native calibration in
`runs/m4/non-electrical-pad-native-2026-10-10/result.json` adds unnumbered stencil
and NPTH shapes to the synthetic M3 circuit fixture. KiCad ERC, geometry,
schematic parity and exact exported netlist all pass; release remains false.
This calibrates serialization and verifier behavior, not the STM32 circuit.

Independent read-only review found no Critical/Important issues. Its Minor
test-coverage observation is addressed: all stencil/NPTH cases now supply old
net/pinfunction/pintype annotations and prove they are cleared, and a combined
duplicate-copper/stencil regression preserves both copper contacts' same net.
The reviewer also checked the installed WSON directly: twelve electrical pad
shapes include four pad9 contacts, and two stencil apertures remain separate.
No deferred Minor findings.

Review scope rulings: candidate datasheet/package/license approval remains
unknown (otherwise wrong pins or unlicensed assets could enter a design);
full-board/routing/manufacturing remain later gates (otherwise a serializer
test could be mistaken for a working board). Native acceptance is synthetic
and unrouted; unconnected items and release eligibility remain explicit.

All seven full-board prerequisite categories remain unresolved. Accepted
real-target assets: zero. Complete support BOM, source-bound pin/pad/package
review, license notices and a real-target circuit bundle must follow before
native STM32 schematic/ERC/bootstrap acceptance. Actual silicon identity,
physical measurements and release confirmations are later human gates.
