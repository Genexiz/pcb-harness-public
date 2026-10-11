# M4 static mechanics evidence — 2026-10-11

The source review now covers all nine interface connectors, exact WIZ550io v1.2 header coordinates and the selected Samtec sockets. It adopts a **60 × 30 × 34 mm whole module/socket reserve**, measured above the host PCB for height. `mating_fit_qualified=false`: the module publisher identifies generic male headers but does not specify their exact part number, post cross-section or free protrusion. No source or machine observation supplies human confirmation or physical mating verification.

The numeric packet is `benchmarks/stm32-communications/mechanical-qualified/`. Manufacturer originals and the imported module board remain ignored under `runs/m4/mechanical-source-2026-10-11/`; earlier frozen originals remain at their existing ignored paths. `source-manifest.json` binds all 16 source documents by path, byte count and SHA256. No redistribution permission was inferred. The Altium conversion is evidence about the purchased Ethernet module; it is not the STM32 host board.

## WIZ550io dimensions and exact revision

The frozen online manual's Mechanical Information says PCB 54 × 26 mm and overall height 24 ± 0.5 mm, without defining the height reference plane. Its linked v1.1 dimension drawing says 55 × 26 mm. The newly recovered [manufacturer v1.2 BOM](https://docs.wiznet.io/assets/files/wiz550io_ver1.2_pl-b50493a3a30767856c71a7bd02519fb4.pdf), physical PDF p1, item 27, explicitly specifies the v1.2 four-layer PCB as **55 × 26 mm, 1.6 mm thick**. Its table title and item 27 identify v1.2 despite legacy v1.1 page headers/footers.

The [linked original v1.2 Altium archive](https://docs.wiznet.io/assets/files/wiz550io_v1.2-4469871907660804dec23ea0fa95bf64.zip) contains `WIZ550io V1.2.PcbDoc`. KiCad 10.0.6 imports it with no reported errors. The report lists 14 unmapped unused internal-plane entries and a missing-font substitution; these are retained rather than treated as electrical or rendering acceptance. Imported Edge.Cuts spans (121.0011, 92.0036)–(176.0011, 118.0036), independently giving 55 × 26 mm. The imported rectangular board center is (148.5011, 105.0036).

Use 55 × 26 mm as the exact-revision design nominal because the original v1.2 PCB and BOM agree. Preserve the manual's conflicting 54 mm claim in the evidence; it is not a tolerance. The supplier provides no planar tolerance here. A larger engineering reserve handles the documented disagreement without inventing a manufacturer guarantee.

The RJ45 outline in exact v1.2 CAD reaches local X=+30.45001 mm, while the board edge is X=+27.5 mm: it overhangs **2.95001 mm**. The old Eagle model gives +30.4 mm. The whole occupied projection is therefore about 57.95 mm long, before any clearance. The earlier 56 mm screening length misses the RJ45 body. The retained older drawing/model also depicts mounting features at Y=±13 mm; the 30 mm width reserve covers their extra projection conservatively. Exact mounting/standoff selection remains part of the actual host floorplan.

## Header datum, orientation and sockets

Coordinates below are the **top projection**, with RJ45 facing +X and KiCad +Y downward. The datum is the center of the rectangular 55 × 26 mm module PCB. Host sockets use the same top projection; do not mirror it merely because the male headers are mounted on the module underside.

| Module header | Host accessory | Pin 1 center, mm | Contact progression | Contact span |
| --- | --- | --- | --- | --- |
| J1, 8 contacts | SSW-108-01-G-S / M1_SOCKET_2 | (7.44, −11.43) | (−2.54, 0) per contact | 17.78 mm |
| J2, 6 contacts | SSW-106-01-G-S / M1_SOCKET_1 | (4.90, +11.43) | (−2.54, 0) per contact | 12.70 mm |

Row spacing is 22.86 mm. J1 contacts become host M1 pads 1–8; J2 contacts become pads 9–14. All 14 exact v1.2 pad centers agree with the retained Eagle-to-KiCad footprint coordinates. This closes documentary applicability of those centers to v1.2. The v1.2 module PCB's own 0.9144 mm header holes are **not** the host socket holes: the two components have different solder tails.

The [Samtec SSW drawing](https://suddendocs.samtec.com/prints/ssw-1xx-xx-xxx-x-xx-xxx-xx-mkt.pdf), Rev CL, physical PDF p1, Fig 1 and Tables 1/2, selects single-row straight −01 contacts. Body length is N×2.54+0.51 mm with ±0.25 mm: 20.83 ±0.25 mm for eight contacts and 15.75 ±0.25 mm for six. Body width is 2.41 mm REF, body height 8.51 ±0.13 mm, and −01 tail length 2.64 ±0.13 mm. Tail section is 0.79 × 0.41 mm REF. The frozen [SSW catalog](https://suddendocs.samtec.com/catalog_english/ssw_th.pdf), physical PDF p1, specifies .025-inch square-post sockets and 3.68–6.35 mm insertion depth.

The nominal rectangular-tail diagonal is 0.89006 mm. A nominal 1.016 mm host hole gives 0.12594 mm diametral clearance. That proves nominal geometric compatibility only: REF tail sizes and a nominal drill do not establish maximum tail size, finished hole tolerance, plating allowance, or solder/process qualification. Assembly/fabrication must agree the finished hole requirements before production.

The module BOM items 9/10 specify 2.54 mm male headers with 8/6 contacts, but provide neither exact header MPN nor actual exposed post length. Require the actual purchased module posts to match the selected socket acceptance and to engage by 3.68–6.35 mm with parallel seating. This is a concrete remaining physical/vendor dependency, rather than an invented fit guarantee.

## Height and access allowance

Conservative stack calculation uses the full documented module maximum, **24.5 mm**, plus the socket maximum, **8.64 mm**, giving **33.14 mm**. It subtracts no insertion overlap because the module height datum and post protrusion are unspecified. Reserve **34 mm above the host board**. The previous 25.5 mm screening height did not include the selected socket stack. Keep other tall components out of the module projection; clearance below it is not guaranteed by these documents.

For the 2.54 mm external headers, the Samtec TSW/HTSW catalog physical PDF p1 specifies −07 total terminal A=10.92 mm, lower tail B=2.54 mm, upper post C=5.84 mm, and the single-row N×2.54 mm body. Nominal height above a flush host PCB is A−B=8.38 mm. Use 9 mm unmated reserve. A selected SSW-style mate with minimum 3.68 mm engagement gives a conservative 13.60 mm static upper stack after adding 0.26 mm header dimensional allowance and the 8.64 mm socket maximum; the adopted 15 mm reserve adds clearance. This does not cover arbitrary oversized harnesses.

| Interface / ref | Exact connector | Nominal body plan, mm | Adopted reserve L×W×H, mm |
| --- | --- | --- | --- |
| USB / J3 | USB4105-GF-A | 7.35×8.94 | 9×10.5×4 unmated; 7 mm selected plug profile |
| UART / J8 | HTSW-103-07-G-S | 7.62×2.54 | 10×5.5×9 unmated; 15 mm selected mate |
| RS-232 / J7 | HTSW-103-07-G-S | 7.62×2.54 | 10×5.5×9; 15 mm selected mate |
| RS-485 / J6 | HTSW-103-07-G-S | 7.62×2.54 | 10×5.5×9; 15 mm selected mate |
| I²C / J9 | HTSW-104-07-G-S | 10.16×2.54 | 13×5.5×9; 15 mm selected mate |
| SPI / J10 | HTSW-106-07-G-S | 15.24×2.54 | 18×5.5×9; 15 mm selected mate |
| Classical CAN / J4 | HTSW-103-07-G-S | 7.62×2.54 | 10×5.5×9; 15 mm selected mate |
| CAN FD / J5 | HTSW-103-07-G-S | 7.62×2.54 | 10×5.5×9; 15 mm selected mate |
| Ethernet / M1 | WIZ550io v1.2 integrated RJ45 | PCB55×26; RJ45-inclusive length≈57.95 | Whole module/socket60×30×34 |

USB dimensions come from the [GCT USB4105 drawing](https://gct.co/files/drawings/usb4105.pdf), Rev B4, physical PDF p1: body height3.31 mm, default two-decimal tolerance ±0.15 mm, PCB land-pattern tolerance ±0.05 mm, plug profile6.5 mm maximum, and1.85 mm minimum mating-view dimension. Its exact footprint's stake/NPTH geometry must stay source-bound. The header dimensions come from [Samtec TSW/HTSW catalog](https://suddendocs.samtec.com/catalog_english/tsw_th.pdf) physical PDF p1, together with its frozen drawing/land pattern. These drawings do not define the adopted clearance boxes.

Adopt 20 mm unobstructed plug/hand insertion corridors outside USB/header board edges and 25 mm at RJ45 for insertion/latch access. These are engineering allowances for an open desktop board; cable bend radius, strain relief and an enclosure are not manufacturer-certified by them. Keep power, keyed SWD, reset/boot and four M3 host mounting locations accessible. SWD remains the source-bound FTSH-105-01-L-DV-K with contact7 removed, with the selected FFSD mate rather than a generic reversed cable.

A 60×30 mm module reserve occupies 1,800 mm² of the10,000 mm² maximum host area. The packet gives coarse disjoint module/core/header zones within100×100 mm as a feasibility screen. Actual placement, mounting clearances, courtyard collisions, pad escape, routing and cable access still require the final host-board layout checks. No PCB floorplan has been accepted by this numeric screen.

## Verification and integration

Fresh validation checks original digests/byte counts, parses PDF revisions/page counts, checks the exact archive member, and compares all14 imported header centers against the preserved independent Eagle coordinates. `validation.json` records the results and `integrity.json` seals the numeric artifacts and all external source/derived paths. Original bytes were moved into ignored runs; the tracked candidate folder contains numeric metadata only.

Parent integration should use `report.json` plus the complete source inventory. Replace the old56×27×25.5 screening values with60×30×34, bind M1 coordinates to the exactv1.2 source, preserve old packets, and keep `mating_fit_qualified=false`, `human_confirmed=false`, `hardware_revision=unknown`. Final layout/production cannot turn physical fit or finished-hole requirements into confirmed facts from this source review.
