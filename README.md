# RP2040 eMMC USB CDC Service Tool

Current branch: `fix/identify-cmd1-1v8-debug`

This repository contains only the active RP2040 eMMC USB CDC stack and its PyQt6 PC service tool.

## Firmware

- RP2040 Pico
- USB CDC serial transport
- eMMC 1-bit interface
  - CMD = GPIO7
  - CLK = GPIO8
  - DAT0 = GPIO9
- Bit-banged command/response path
- PIO-assisted DAT0 read path for block operations
- eMMC IDENTIFY / CID / CSD / EXT_CSD / GPT / dump and diagnostic commands

Build:

```bash
mkdir build
cd build
cmake ..
cmake --build . -j
```

The generated UF2 is:

```
build/emmc_reader_writer.uf2
```

## PC application

The active GUI is under `chatgpt/`:

```
python main.py
```

It communicates directly with the RP2040 USB CDC command protocol.

Active service areas:

- IDENTIFY
- BOOT / EXT_CSD
- USER AREA
- HEALTH
- SPECIAL TASK
- ISP TEST

No network/WebSocket/MapleLink transport is part of the active stack.

## USB CDC command examples

```
INIT
VERSION
CHECK_PINS
IDENTIFY
READ_EXTCSD
GPT
CMD_TEST 6
CMD1_TEST 16 1090482176
SD_TEST 24 1090482176
CLK_TEST 400000 1000
PIN_TEST CMD HIGH
PIN_TEST CLK HIGH
PIN_TEST DAT0 HIGH
STOP
```

## CMD1/R3

The firmware parses the 48-bit eMMC R3 response according to the eMMC response layout:

- START = 0
- TRANSMISSION = 0
- reserved [45:40] = 111111
- OCR [39:8]
- reserved [7:1] = 1111111
- END = 1

R3 is not CRC-protected; the fixed reserved fields must not be treated as a CRC.

## Project scope

Only source files required by the active USB CDC eMMC firmware and the active PyQt6 eMMC GUI are kept in this repository.
