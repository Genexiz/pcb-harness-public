# Third-party components

PCB Harness's own code is licensed under Apache-2.0 (`LICENSE`). The files
below keep their original licenses and are not relicensed. Pinned origins and
SHA-256 hashes are in `benchmarks/stm32-communications/firmware-full/sources.lock.json`.

## Bundled firmware sources (`benchmarks/stm32-communications/firmware-full/vendor/`)

| Path | Origin | License |
|---|---|---|
| `cmsis/core` | Arm CMSIS via STM32CubeF1 v1.8.6 | Apache-2.0 (`cmsis/LICENSE.txt`) |
| `cmsis/device`, `cmsis/startup_*.s`, `cmsis/system_*.c` | STMicroelectronics cmsis_device_f1 | Apache-2.0 (`cmsis/device-LICENSE.md`) |
| `hal` | STMicroelectronics stm32f1xx_hal_driver | BSD-3-Clause (`hal/LICENSE.md`) |
| `usb` | STM32_USB_Device_Library from STM32CubeF1 v1.8.6 | ST SLA0044 "Ultimate Liberty": use only with ST microcontrollers; notices retained in each file. See https://www.st.com/SLA0044 |
| `wiznet` | WIZnet ioLibrary_Driver v3.2.0 | MIT (`wiznet/license.txt`) |
| `cube-License.md` | STM32CubeF1 component license table | — |

`adapters/stm32f1xx_hal_pcd_bounded.c` is a patched derivative of the ST HAL
PCD driver (BSD-3-Clause). The patch and hashes are in `adapters/`.

## Not redistributed: Microchip MCP251xFD CAN FD SPI API

Microchip licenses this API "exclusively with Microchip products" and grants no
explicit redistribution right. The public repository omits
`vendor/microchip/canfdspi/` and `vendor/microchip/readme.h`. Fetch and
hash-verify them from Microchip's official archive:

```sh
.venv/bin/python benchmarks/stm32-communications/firmware-full/fetch_microchip.py
```

`vendor/microchip/spi/drv_spi.h` is this project's STM32 transport replacement.

## KiCad library footprints

Footprints under `benchmarks/stm32-communications/support-qualified/library*/`
and `source-recovery/assets/` are copied or derived from the KiCad libraries
(https://gitlab.com/kicad/libraries). Those libraries are licensed under
CC-BY-SA 4.0, with an exception that allows their use in designs without
affecting the design's license (https://www.kicad.org/libraries/license/).
Modified footprints remain under CC-BY-SA 4.0.

## Manufacturer documents and CAD

Datasheets, drawings and manufacturer CAD (for example the WIZnet WIZ550io
Eagle/Altium files) are never redistributed. They are retrieved into ignored
`runs/` directories and referenced by URL and SHA-256 only.
