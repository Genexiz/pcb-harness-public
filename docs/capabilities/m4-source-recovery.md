# M4 original publisher source recovery — 2026-10-10

Recovered all three missing ST original PDFs from the canonical manufacturer URLs. These are original PDF payload bytes saved without rewriting; HTTP content decoding only is performed by the client. They are not web text exports, print-to-PDF files, community attachments, mirrors, or synthesized PDFs. `pypdf` verifies the `%PDF-` signature, parseability, full page count, and revision text. Key pinout, DMA, errata-applicability and TI package pages were also rendered and visually inspected.

| Source | Original bytes | SHA256 | Verified locator |
| --- | ---: | --- | --- |
| [DS5319 Rev 20](https://www.st.com/resource/en/datasheet/stm32f103c8.pdf) | 1965230 | `1e54ce18e6c34c5b4a78986f26e245e143748c721009fc9af5953795c30686bc` | Table 2 PDF p10; Figure 8 LQFP48 pinout PDF p26; Table 5 pin definitions PDF pp28-33; LQFP48 package PDF pp98-100; revision history PDF p113 |
| [RM0008 Rev 21](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf) | 13119424 | `4c1b8ac2729cc1f45a4685eea9e91e6139e24e58804fba21e27201dfcc2ad149` | Section 13.3.7, Figure 50 DMA1 mapping PDF p281, Table 78 PDF p282; AFIO_MAPR PDF pp177-181; SPI chapter 25; I2C chapter 26; USART chapter 27; USB chapter 23 |
| [ES096 Rev 15](https://www.st.com/resource/en/errata_sheet/es096-stm32f101x8b-stm32f102x8b-and-stm32f103x8b-mediumdensity-device-limitations-stmicroelectronics.pdf) | 956332 | `7bcdf58d8b602292d68abb59e181a4f44a038f215d8b01b0167f6d7139285490` | Table 1/2 applicability and REV_ID PDF p1; Table 3 per-silicon limitation matrix PDF pp2-4; I2C Section 2.8 PDF pp17-20; USB Section 2.12 PDF pp23-24 |
| [MAX3232 SLLS410O, current TI package addendum](https://www.ti.com/lit/ds/symlink/max3232.pdf) | 1783899 | `484d6bb1c92c5f2e993f1f3835c574bc4c03fea4b4d70a5e690b8d52674acf37` | MAX3232IDWR Active SOIC(DW),16,-40..85C orderable row PDF p15 (addendum date 23-Dec-2025); DW0016A drawing PDF p24, board/stencil layout PDF pp25-26 |
| [MAX3232IDWR exact orderable page](https://www.ti.com/product/MAX3232/part-details/MAX3232IDWR) | 83469 | `6178505d1302d9c6fe18d35f5a2ca8360a6d3958c666e002ce7f89a732679474` | Original HTML meta description lines114,128; structured additionalProperty ACTIVE_true line146; packaging SOIC(DW)|16 line1686 |
| [MAX3232IDWR carrier report](https://www.ti.com/packaging/docs/carriermaterial/downloadCarrierReport?OPN=MAX3232IDWR) | 129296 | `320eeed439d886745b4c2b4c3a7af56257c410a6e6219971af3626bc5941e5a1` | PDF p1 exact MAX3232IDWR; PackageName DW, PackageType SOIC,16 pins,SPQ2000 |

## Successful route and reproducibility

System curl 8.7.1 with HTTP/2 returned stream INTERNAL_ERROR. HTTP/1.1 timed out without payload. Alternate CD aliases, legacy official content aliases, no-www redirect, regional ST host, TLS1.2, Python urllib and Node HTTP/2 did not recover ST bytes. The in-app browser rejected direct PDF navigation with `net::ERR_BLOCKED_BY_CLIENT`; the CUA attempt to use Safari reported `Computer Use was not approved to use Safari`. No user permission request was made and no native browser interaction followed.

The maintainer retrieved the three canonical ST PDFs from their st.com URLs; canonical URL, effective URL, response headers, attempt time, byte count and SHA-256 are retained locally. Retrieval tooling is not distributed. TI exact part/carrier and current datasheet were retrieved directly with curl.

`recovery-manifest.json` records all six recovered documents; `benchmarks/stm32-communications/source-recovery/recovered-sources.json` provides a source-integration supplement. Original files are in `runs/m4/source-recovery-2026-10-10/sources/`. The historical `sources.lock.json` and earlier reports are untouched; recovered ST entries are recorded separately in `qualified-design/sources.lock.json`. All `human_confirmed` values remain false; this recovery proves source retrieval and documentary matches, and does not supply human sign-off or determine actual purchased STM32 silicon revision.

## Exact RS-232 orderable correction

The current TI datasheet addendum is dated 23-Dec-2025. It contains an explicit **Active MAX3232IDWR** row: SOIC(DW),16 pins,-40 to85°C. The exact manufacturer part page also reports ACTIVE. Its DW0016A mechanical drawing (PDF p24) has body width7.4–7.6mm, length10.1–10.5mm, pitch1.27mm, lead span9.97–10.63mm and maximum height2.65mm. PDF pp25–26 give the corresponding board/stencil patterns. The carrier report corroborates exact MAX3232IDWR→DW→SOIC→16.

The exact MAX3232IDR part page returned HTTP404, and the current datasheet has no exact MAX3232IDR row. Its downloadable carrier report returned a PDF with a title and disclaimer but **no package rows**; that response is preserved in attempts/005 and rejected as package proof. MAX3232IDRG4 appears as obsolete SOIC(D), but this does not establish exact unsuffixed MAX3232IDR status by itself. The parent-approved alternative is MAX3232IDWR; it requires a **wide SOIC DW footprint**, not the earlier narrow SOIC(D) footprint. A new BOM/package revision must preserve this distinction. Source retrieval itself has no external blocker remaining.

## Validation boundaries

PDF page locators here are one-based physical PDF pages. DS5319 contains114 physical PDF pages even though some interior footers say `/115`; first-page footer and parser both establish114. ES096's first page says March2022; product metadata update dates need not be identical to document publication month. Machine validation and rendered-page inspection are retained as evidence without setting human confirmation.

## Reusable completion packet

`pcb_harness.orchestration.source_completion` captures the six recovered documents
into a fresh local packet and reconstructs derivatives from calibrated originals.
The inputs are `completion-input.json`, `observations-v1.json`, `page-checks.json`
and a preserved KiCad wide SOIC template, all under
`benchmarks/stm32-communications/source-recovery/`. Forty-five physical PDF pages
are extracted and frozen, including the complete MCU pin-table pages,
package/ordering scheme, DMA request table, silicon applicability matrix and
selected errata sections. Original-file digests, extracted-page content and
observations are separate evidence. Runtime loading needs no network access,
PDF dependency, provider account or key.

```python
from pcb_harness.orchestration.source_completion import (
    capture_source_completion, verify_source_completion,
    load_source_completion, apply_source_completion,
)

capture_source_completion(
    "benchmarks/stm32-communications/source-recovery/completion-input.json",
    repository_root, fresh_packet_path,
)
verify_source_completion(fresh_packet_path)
evidence = load_source_completion(fresh_packet_path)
parts, asset_bytes, evidence = apply_source_completion(
    fresh_packet_path, original_parts, original_asset_bytes,
)
```

Returned evidence contains circuit-schema `documents` and `facts`, plus `mcu`,
`rs232_correction` and `report`. MCU evidence includes all48 physical pins,
source-bound default peripheral observations,64KiB Flash,20KiB SRAM, DMA request
mappings, REV_ID aliases and17 planned errata responses. Responses remain
`planned-not-verified`; physical device marking and REV_ID remain null. Resource
availability does not prove implemented concurrency or timing.

`apply_source_completion` returns new objects, preserving inputs. It retains
historical `part_id`/`symbol_id` `MAX3232IDR` so old topology identities resolve,
but replaces the purchasing MPN with `MAX3232IDWR`, changes the package to DW
and creates `STM32Target:MAX3232IDWR_DW`. Pads use TI's example board geometry
from physical PDF p25:16 pads of2.00x0.60mm,9.30mm opposing-row center spacing
and1.27mm pitch. The frozen KiCad template is
`Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm`; its2.05mm pad length is changed to
TI's2.00mm example. Assembly-site mask/paste/land-pattern acceptance remains
pending. The derivative updates the shared symbol's Value/Footprint properties
and all referring symbol hashes. The narrow footprint is omitted when unused.
Old core packets and source locks remain independently preserved.

Before attaching the recovered MAX3232 pinout facts, the producer checks all 16
part pin numbers/names, unique pin identities, the exact pin→symbol→pad mapping
and all 16 symbol pin numbers/names against the frozen observations. A caller
cannot make an incompatible symbol pass by recalculating its asset digest.

The caller must also apply
`evidence["rs232_correction"]["topology_value_patch"]` to U7 topology/BOM Value:
`{"ref": "U7", "value": "MAX3232IDWR"}`. For circuit-packet integration, freeze
this entire packet under `inputs/source-completion`, include its complete
integrity inventory and call the same APIs during rederivation. `stm32_circuit`
owns this outer integration.

The packet writes `source-manifest.json`, original `sources/`, checked inputs,
`documents.json`, `facts.json`, `mcu-source-evidence.json`,
`rs232-correction.json`, `report.json` and `integrity.json`. Verification rejects
missing/duplicate sources, wrong publisher URLs, original-file drift, changed
checked observations/pages, unexpected fields, unsafe local paths and changed
derived claims even when an editor updates artifact hashes. New documentary
revisions need a fresh audit and explicit calibration update.

## Reproduction and validation

```sh
.venv/bin/python -m pcb_harness.orchestration.source_completion \
  --repository-root . \
  --output runs/m4/source-completion-2026-10-10
```

Exit status2 denotes unconfirmed documentary evidence; it is not M4/release
acceptance. Audit complete PDF page counts/revisions and reproduce all45 page
extractions with the optional `pypdf` tool:

```sh
<python with pypdf> \
  benchmarks/stm32-communications/source-recovery/validate_checked_pages.py
```

Checked result:6 original documents,5 full parsed PDF revisions and45 exact page
extractions. Original HTML is checked separately for exact orderable, ACTIVE
metadata and SOIC(DW) package text. Focused source-completion tests pass18 cases,
including source rehash forgery, fact drift, all shared-symbol hashes and
self-rehashed derived claims. Three capture-admission negatives run without
optional downloads; original-byte integration tests explicitly skip when the
recovery run is absent.

The source agent's sandboxed fullsuite produced609 passes and23 failures:
21 native PCB DRC/bootstrap/fabrication checks encountered KiCad abort `-6`,
and two restart checks lacked boot epoch. Parent reproduced the sandbox's
PCB DRC abort and denied `sysctl` access, then ran the identical affected tests
outside the sandbox:46 passed in6.96s. No product change was needed for these
sandbox limitations; parent owns final whole-change verification.

## Clock pin scope

Changing from a crystal to an active HSE oscillator leaves the source pin
inventory intact: DS5319 Figure8/Table5 identify PD0/OSC_IN as physical pin5 and
PD1/OSC_OUT as pin6. Live inspection of retained RM0008 physical PDF p95 requires
OSC_OUT hi-Z in HSE bypass; DS5319 physical PDF p50/Table20 gives external-clock
electrical/timing limits. Those two extra pages are outside the fixed45-page
extraction and should be separately source-bound by the circuit/oscillator
producer. Pin capabilities do not require a crystal connection in bypass mode.

## Fresh continuation verification — 2026-10-11

The fresh packet is `runs/m4/source-completion-2026-10-11`. Capture and independent
reload/derivative verification pass with 6 original sources, 45 checked physical
PDF pages, 31 unconfirmed facts, 48 MCU pins, 12 DMA requests and 17 planned errata
responses. The optional original-byte/page audit also passes: 6 documents,
5 parsed PDF revisions and 45 exact page extractions. Source retrieval has no
remaining dependency. No original files or earlier packets were changed.

Focused verification is 24 tests passed. Six new admission regressions were
observed failing before the fix and passing after it: incorrect part pin name,
duplicate part pin, wrong pad mapping, wrong symbol mapping, incorrect
self-rehashed symbol pin name and duplicate self-rehashed symbol pin.

`human_confirmed=false`, physical silicon marking and REV_ID remain null, and
errata responses remain `planned-not-verified`. The source packet's CLI exit 2
continues to mean documentary evidence only. Critical fact review, physical
silicon identification, implementation/hardware errata verification and
assembly/circuit acceptance remain downstream requirements. Parent integration
owns the complete unsandboxed suite and final milestone result.
