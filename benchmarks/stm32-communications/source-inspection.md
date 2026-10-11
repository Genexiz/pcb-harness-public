# M4 source inspection, 2026-10-10

This is automated document inspection, not human fact confirmation. Original
snapshots for seven sources are retained with SHA-256 in `sources.lock.json`;
ST documents were readable through web retrieval but full-file download failed.
No hash of a missing original PDF was invented.

Engineering continuation: eight of eleven snapshots retained after appending
the WIZnet dimension drawing; original seven hashes and ST failures preserved.
DS5319/ES096 were inspected again through the web. Four outside-sandbox canonical/
legacy ST endpoint attempts timed out after25s with zero bytes. Prior `.pdf`
files containing publisher error HTML were excluded, not treated as originals.
New source-copy/retrieval notes are in `runs/m4/sources/engineering-2026-10-10`.

`engineering.json` binds each usable observation to its original-file digest;
ST and support-part facts retain null hashes and stay unresolved. The dossier
records supply ranges and conditional current limits, rather than translating
no-load/typical values into full operating maxima. CAN transceiver VIO is now
explicit on3V3 with2mA combined reserve; direct5V VDD remains separate. TPS62162
initial PSM tolerance differs from PWM, and the JEDEC thermal metric cannot
validate the chosen PCB copper/loss. `circuit-draft.md` lists exact core pin
connections and source-dependent support-component requirements.

The linked WIZ550io v1.1 drawing, stated dimension-compatible with v1.2 by the
manual, labels55mm overall horizontal extent while the page says54mm PCB length.
Different reference planes may explain it, but no resolution was established.
Keep `MECHANICAL_CONFLICT`;56x27x25.5mm is only conservative screening. Header
origins, socket height and exact connector/mating envelopes remain unreviewed.

ES096 Rev15 inspection supplies17 targeted planned policies: default SPI1 remap,
TIM1/USART1 coexistence, DMA flag/access handling, I2C critical receive events,
START/BERR timeouts, analog-filter BUSY recovery and100kHz repeated-start
conditions, UART framing without sole dependence on IDLE, SPI hardware CRC
conflict with UART DMA, and USB suspend/resume/PMA/low-APB constraints. Physical
marking and REV_ID, full-table applicability and implemented firmware remain
unknown. REV_ID0x2003 does not distinguish all Y/X/1/2/3 markings.

- [ST DS5319 Rev20](https://www.st.com/resource/en/datasheet/stm32f103c8.pdf),
  Table5/Figure8: C8 target is 64KB flash/20KB SRAM, LQFP48. Default USART1
  PA9/PA10, USART2 PA2/PA3, USART3 PB10/PB11; SPI1 PA5/6/7, SPI2 PB13/14/15;
  I2C1 PB6/PB7; USB PA11/PA12; reserve SWD PA13/PA14 and boot/clock/power.
  The allocation supports native USB and external CAN; package pin numbers and
  full operating/clock conditions still need retained-source circuit review.
- [RM0008](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf):
  USART DMA requests compete with both SPI and I2C requests. Use three UART DMA
  TX/RX pairs, both SPIs without DMA and I2C interrupts. This is a proposed
  firmware policy; silicon performance has not been tested. Current manual
  snapshot and revision-specific errata remain missing from local evidence.
- [ES096 Rev15](https://www.st.com/resource/en/errata_sheet/es096-stm32f101x8b-stm32f102x8b-and-stm32f103x8b-mediumdensity-device-limitations-stmicroelectronics.pdf):
  selected silicon revision and I2C/USB workaround assessment are unresolved.
- [MCP2518FD DS20006027B](https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ProductDocuments/DataSheets/External-CAN-FD-Controller-with-SPI-Interface-DS20006027B.pdf):
  SOIC14 candidate, external SPI CAN FD controller, up to 20MHz SPI,
  2KB controller RAM, selectable CAN2.0B mode. Table7-1 documents 20mA maximum
  supply current under 40MHz SYSCLK/20MHz SPI conditions. Two controllers are
  retained; eight RX slots each is an allocation assumption, not a complete
  validated FIFO/TX/TEF RAM map. Clock/crystal, reset, interrupt polarity and
  full controller setup remain circuit/firmware work.
- [WIZ550io manual](https://docs.wiznet.io/Product/ioModule/wiz550io):
  J1 carries SPI/3V3/GND; J2 carries RDY/RSTn/INTn and power. Current table lists
  141mA **typical**, no maximum. Do not reuse 132mA from W5500/W5500-io as a
  maximum for this module. The candidate is v1.2; online version history also
  describes v1.3. Freeze exact header/body/height drawings for the selected
  module before mechanical acceptance. The v1.2 schematic is retained.
- [THVD1450](https://www.ti.com/lit/ds/symlink/thvd1450.pdf):
  SOIC8 RS485 candidate, native 3.3V operation and half-duplex direction control.
  Exact receiver/driver wiring, termination/bias, load/current and protection
  remain to be drawn and reviewed.
- [MAX3232](https://www.ti.com/lit/ds/symlink/max3232.pdf):
  SOIC16 candidate, 3–5.5V operation, charge-pump capacitors required. Only TX/RX
  are target functions; unselected channels require a deliberate circuit policy.
  Capacitor selection must use operating conditions, not the typical headline.
- [TPS6216x SLVSAM2E](https://www.ti.com/lit/ds/symlink/tps62160.pdf):
  TPS62162 is the fixed3.3V variant, WSON8 exposed-pad package, up to1A.
  Select inductor/capacitors and connect VOS/FB/grounds as the fixed variant
  requires. Efficiency curves are typical; the 80% estimate is an engineering
  reserve, not a manufacturer-guaranteed lower bound. Thermal acceptance needs
  actual copper/ambient/load/loss evidence.
- [MCP2561/2FD DS20005284A](https://ww1.microchip.com/downloads/en/DeviceDoc/20005284A.pdf):
  MCP2562FD SOIC8 uses 5V supply with separate VIO for 3.3V logic, supporting
  the selected2Mbit/s FD data phase. Include its direct5V load in the power
  budget rather than pretending all CAN circuitry is on3V3. The exact current,
  standby, termination and protection circuit needs further review.
