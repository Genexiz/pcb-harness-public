# STM32 communications circuit draft

Date: 2026-10-10. Status: candidate topology and component requirements, not an
accepted schematic/netlist, purchase BOM or fabrication-ready design. All nine
interfaces and the direct STM32F103C8T6 LQFP48 target remain present.
Source IDs/hashes/locators are in `engineering.json` and `sources.lock.json`.
This draft supplies concrete connections for the next exact-BOM/asset stage.

## Supply and MCU

External regulated 5 V is the main supply. Choose a 5 V +/-5% input contract;
the 3V3 rail must stay within 3.135-3.465 V at every consumer including ripple,
load steps, connector loss and startup. These are engineering requirements,
not measured regulator outputs. No USB VBUS connection to either supply rail.
Header loads collectively use a 50 mA reserve shared with LEDs/pullups; exact
current allocation/protection is still required. An external device must not
back-power the board via an IO or supply header.

TPS62162DSGR core connections: pin1 PGND, pin2 VIN=5V, pin3 EN to the selected
enable network, pin4 AGND, pin5 FB=AGND for the fixed variant, pin6 VOS to the
regulated output, pin7 SW to the inductor, pin8 PG to a 3V3 pullup/test point,
exposed pad to ground. The initial LC candidate is 2.2uH / 22uF output plus
10uF input; use the stable LC combinations and actual effective capacitance,
inductor saturation/DCR/current-limit behavior and tight switching loops from
[TI SLVSAM2E](https://www.ti.com/lit/ds/symlink/tps62160.pdf), pp4,14-16,26-27.
Exact L/C MPNs and bias curves are not selected. PSM initial tolerance differs
from PWM; neither includes the complete transient/line/load/ripple budget.
The WSON JEDEC theta-JA61.8C/W is a reference, not this board's thermal model.

MCU VDD pins24/36/48 and VDDA9 connect to 3V3; VSS23/35/47 and VSSA8 to GND;
VBAT1 also to 3V3 because no battery is planned. Provide local bypass for each
power group and bulk capacitance, with values/placement grounded in retained
ST hardware guidance before accepting assets. NRST7 has accessible reset and
SWD reset; BOOT0 pin44 defaults low with boot jumper to3V3; PB2/BOOT1 pin20
defaults low. SWD pins34/37 plus NRST/GND/3V3 go to a keyed programming header.
HSE uses PD0/PD1 pins5/6 and an 8MHz crystal candidate; PLL yields72MHz CPU,
APB1=36MHz, USB=48MHz. Crystal MPN, ESR/CL and capacitors require source review.
PC14/PC15 are reserved. Package, clock and reset facts remain gated by the
missing original DS5319/RM0008 snapshots.

## USB-C device

USB is FS CDC device only. Select a USB2-only USB-C receptacle with exact pad
map/mechanical drawing, join duplicate D+ and D- contacts as the connector
requires, and connect to PA12 pin33 / PA11 pin32 through reviewed ESD/series
components. CC1 and CC2 each get an independent nominal5.1kohm Rd to ground.
Supply sense uses PA0 pin10 with an off-state-safe isolation network; a bare
VBUS divider is not accepted without unpowered injection/backfeed review.
Provide the required external D+ pullup and choose a disconnect policy that
cannot assert attachment while VBUS or the board supply is absent. Shield
connection and ESD return require deliberate circuit/layout review. Connector,
ESD array, pullup-control/sense parts and USB source grounding remain open.

## UART / RS-232 / RS-485 / headers

UART3V3 header: PA9 pin30 TX, PA10 pin31 RX, GND and a clearly labeled optional
3V3 supply. No RTS/CTS. Protect the unpowered board and label3V3 logic.

MAX3232IDR: USART3 PB10 pin21 -> DIN1 pin11; ROUT1 pin12 -> PB11 pin22.
DOUT1 pin14 -> external TX, RIN1 pin13 <- external RX; connector includes GND.
Pin16=3V3, pin15=GND. C1 spans pins1/3, C2 pins4/5; storage capacitors connect
V+ pin2 and V- pin6 to ground per the reference circuit. At3.3V, start with
four nominal0.1uF pump capacitors and local bypass; select bias/tolerance so
effective values meet the relevant operating case. Tie unused DIN2 pin10 to
a valid logic level; unselected output/receiver policy is to be reviewed.
No-load ICC1mA is not the loaded TX/charge-pump bound.
[TI SLLS410O](https://www.ti.com/lit/ds/symlink/max3232.pdf), pp3-6,11-12.

THVD1450DR: USART2 PA2 pin12 -> D pin4; R pin1 -> PA3 pin13. Tie DE pin3 and
active-low RE pin2 to RS485_DE PA1 pin11 so receive is active when transmit is
disabled. Pin8=3V3, pin5=GND; A pin6 / B pin7 / GND go to the bus connector.
Default DE low at reset. Add local bypass; optional120ohm termination, disabled
by default, with an explicitly labeled enable. Bias provision is optional and
must not fight the remote network; confirm total loading/cable topology before
populating. Read VOD/current and dissipation for the actual load rather than
using quiescent ICC3mA. [TI SLLSEY3E](https://www.ti.com/lit/ds/symlink/thvd1450.pdf), pp5,9-11.

I2C1 PB6/PB7 pins42/43 -> SCL/SDA plus GND/optional3V3. Start with4.7kohm
pullups as an engineering candidate, then calculate pullup range against
capacitance, sink current and ES096 repeated-start conditions at100kHz.
Default SPI1 PA5/6/7 pins15/16/17 -> SCK/MISO/MOSI; PB9 pin46 is external CS.
Header includes GND and optional3V3, no unqualified5V IO. Require high-Z MISO
when deselected, short bounded external transactions and compatible modes.
Internal clients use9MHz; header562.5kHz is budgeted at500kHz. Pull all CS high
during boot and switch SPI mode/divider only when every CS is inactive.

## Two independent external CAN networks

Each MCP2518FD-E/SL uses a dedicated40MHz crystal candidate on OSC2 pin5 / OSC1
pin6; supply pin14=3V3, pin7=GND, local bypass. Shared SPI1 goes to SCK10,
SDI11 and SDO12. U2 nCS13=PA4 pin14, INT4=PB0 pin18; U3 nCS13=PA8 pin29,
INT4=PB1 pin19. Configure active-low interrupts explicitly; provide pullups
for open-drain mode. CLKO3 and unused GPIO8/9 have deliberate NC policies
unless the final transceiver standby policy uses XSTBY. No native bxCAN.
[Microchip DS20006027B](https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ProductDocuments/DataSheets/External-CAN-FD-Controller-with-SPI-Interface-DS20006027B.pdf), Table1-1, message-object figures and Table7-1.

For each paired MCP2562FD-E/SN: TXD1 <- controller TXCAN1, RXD4 -> controller
RXCAN2, VDD3=5V, VIO5=3V3, VSS2=GND. CANL6/CANH7 plus signal-ground go to a
separate connector. Default STBY8 low for normal operation, with a testable
standby provision if added; it cannot float. Local bypass is required on both
rails. Selectable120ohm endpoint termination, disabled by default; choose bus
protection rated for the transceiver/common-mode conditions and actual2Mbit/s
FD topology. VDD and VIO current are accounted separately; fault current is
not covered by the steady-state reserve.
[Microchip DS20005284A](https://ww1.microchip.com/downloads/en/DeviceDoc/20005284A.pdf), Table1-2, p9 DC conditions.

Controller RAM allocation (addresses in device RAM, end exclusive):

| Network | TEF8 timestamped | TX FIFO8 | RX FIFO8 timestamped | Total/free |
| --- | --- | --- | --- | --- |
| Classical8B | 0x400-0x460 | 0x460-0x4E0 | 0x4E0-0x580 | 384/1664B |
| FD64B | 0x400-0x460 | 0x460-0x6A0 | 0x6A0-0x900 | 1280/768B |

TXQ disabled. Use TEF then FIFO1 TX then FIFO2 RX so hardware allocation order
matches this draft; verify user-address registers during bring-up. Initialize
RAM/ECC before use and set payload/timestamp/depth fields consistently.
Nominal500kbit/s at40MHz uses BRP1, TSEG1=63, TSEG2=16, SJW16; FD data2Mbit/s
uses BRP1, TSEG1=15, TSEG2=4, SJW4. Both sample at80%. Register fields are
values minus1. These arithmetic configurations still need clock-tolerance,
propagation/oscillator and TDC configuration review plus functional drivers.

## Ethernet module and mechanics

WIZ550io v1.2: J1 pins1/2 GND,3 MOSI(PB15),4 MISO(PB14),5 SCK(PB13),6 SCSn
(PB12),7/8 3V3. J2 pin1=3V3,2 RDY(PC13),3 RSTn(PB5),4 NC,5 INTn(PB8),6 GND.
Use HW reset and wait for RDY; validate pulse width/readiness timing from the
retained revision. The integrated RJ45 and magnetics stay on the module.

[WIZnet manual](https://docs.wiznet.io/Product/ioModule/wiz550io) gives54x26mm;
its linked [v1.1 dimension drawing](https://docs.wiznet.io/img/products/wiz550io/wiz550io_v1.1_dimension.png)
labels55mm overall. The manual says v1.2 shares dimensions, but origin/reference
planes are unresolved. Screening reserves56x27x25.5mm; this is a conservative
body allowance, not an approved footprint/courtyard or connector layout.
Do not derive pin origins from the cropped illustration. Socket seating
height, full envelope, insertion access and exact mating parts remain open.

Four accessible M3 mounting holes on a board no larger than100x100mm, with
top-side SMD and test points for5V/3V3/NRST/boot/CS/interrupts, remain target
requirements. Exact hole diameter/edge keepouts and connector/panel insertion
envelopes depend on the selected fabrication/mechanical profile.

## Remaining prerequisites

Choose exact crystals/L/C/resistors/connectors/protection parts with operating
and pin/pad documents; freeze their symbols/footprints and licenses; translate
this draft into an M3 real-target bundle and independently review it before
native ERC/bootstrap/parity. Implement/test the17 targeted ES096 policies in
`engineering.json` and review the full errata table; record actual marking and
REV_ID. Complete nine-interface firmware and bounded scheduling remain open.
Manufacturing service/stackup, actual power loss/thermal and module load limits
also remain open. No source observation or software test removes those gates.
