# OptiSender

A Python bridge that reads raw swing data from an **OptiShot 2** golf simulator mat over USB HID and forwards calculated ball-flight telemetry to **OpenGolfSim** via a TCP socket API.

Logic and packet structure were ported from the [RepliShot](https://github.com/RepliShot) C++ project (`usbcode.cpp`, `shotprocessing.cpp`). The Python layer adds a physics/ball-flight engine and a simulation mode for development without hardware.

---

## Table of Contents

1. [Requirements](#requirements)
2. [Installation](#installation)
3. [Running](#running)
4. [Data Flow Architecture](#data-flow-architecture)
5. [HID Hardware Reference](#hid-hardware-reference)
6. [Packet Format (60-byte HID Report)](#packet-format-60-byte-hid-report)
7. [Physics & Tuning](#physics--tuning)
8. [Simulation Mode](#simulation-mode)
9. [Technical Gotchas](#technical-gotchas)
10. [File Reference](#file-reference)

---

## Requirements

| Dependency | Purpose |
|---|---|
| `hidapi` (via `hidapi-0.15.0-cp315-cp315-win_amd64.whl`) | Low-level USB HID communication with OptiShot 2 |
| `pynput` | Non-blocking keyboard input for club cycling and sim triggers |
| Python 3.15 (Windows x64) | Matches the bundled `.whl` ABI tag |

---

## Installation

```bash
# 1. Install the bundled hidapi wheel (must match your Python version/arch)
pip install hidapi-0.15.0-cp315-cp315-win_amd64.whl

# 2. Install remaining dependencies
pip install pynput

# 3. On Windows you may need WinUSB/libusb-1.0 driver installed for the OptiShot device.
#    Use Zadig (https://zadig.akeo.ie) to replace the vendor driver with WinUSB for:
#      VID: 0x0547  PID: 0x3294
```

> If `pynput` is unavailable the program still runs, but keyboard club cycling and simulation triggers are disabled.

---

## Running

```bash
python OptiSender.py
```

On startup:
- If the OptiShot 2 is detected, hardware mode activates.
- If the device is not found, **simulation mode** activates automatically.
- The program attempts to connect to the OpenGolfSim API at `127.0.0.1:3111` and retries every 5 seconds if the connection fails.

**Keyboard controls (requires `pynput`):**

| Key | Action |
|---|---|
| `↑` / `↓` | Cycle club selection |
| `S` or `Enter` | Trigger simulated swing (simulation mode only) |

---

## Data Flow Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      OptiShot 2 Mat                     │
│  Back Sensor Row (8 LEDs)  ←  Ball crosses back row     │
│  Front Sensor Row (8 LEDs) ←  Ball crosses front row    │
└────────────────────┬────────────────────────────────────┘
                     │ USB HID (VID 0x0547 / PID 0x3294)
                     ▼
┌─────────────────────────────────────────────────────────┐
│                     OptiReader                          │
│  opti_reader.py                                         │
│  • Opens device, sends CMD_SENSORS_ON (0x50)            │
│  • Sets LED green (ready)                               │
│  • Reads 60-byte packets (non-blocking)                 │
│  • Controls LED: red (processing) / green (ready)       │
└────────────────────┬────────────────────────────────────┘
                     │ raw list[int], 60 bytes
                     ▼
┌─────────────────────────────────────────────────────────┐
│                     OptiFilter                          │
│  data_filters.py                                        │
│  • Duplicate guard (byte-for-byte compare vs prev)      │
│  • Validity check: packet must contain both 0x81        │
│    (back row) AND 0x4A (front row) opcodes              │
└────────────────────┬────────────────────────────────────┘
                     │ validated raw packet
                     ▼
┌─────────────────────────────────────────────────────────┐
│                   ShotProcessor                         │
│  shot_processor.py                                      │
│                                                         │
│  PASS 1 — Speed & Ball Detection                        │
│  • Iterates 5-byte chunks, accumulates elapsed_time     │
│  • Detects ball hit by gap anomaly (gap > 0x25 then     │
│    confirmed < 0x20 on next 0x4A opcode)                │
│  • Computes swing speed:                                │
│      speed = (SENSOR_SPACING / (elapsed * 18)) * 2236.94│
│  • Tracks min/max active LED bits across back/front rows│
│  • Derives smash_factor from back-row contact position  │
│                                                         │
│  PASS 2 — Face Angle (Trigonometric)                    │
│  • Per-chunk: measures lateral shift of active LEDs     │
│    between consecutive chunks (y in LED units)          │
│  • x_travel = speed_per_tick × ticks                   │
│  • angle = atan(x / y) in degrees                       │
│  • Weighted average: (front_avg + 2×back_avg) / 3       │
│                                                         │
│  Returns: speed, face_angle, path, contact, smash_factor│
└────────────────────┬────────────────────────────────────┘
                     │ metrics dict
                     ▼
┌─────────────────────────────────────────────────────────┐
│                   PhysicsEngine                         │
│  ballphysics.py  +  tuning.json                         │
│                                                         │
│  • Ball Speed   = club_speed × smash − contact_penalty  │
│  • Launch Angle = base_VLA + (face_angle × 0.3)         │
│  • Horiz. Angle = (face × 0.85) + (path × 0.5)         │
│  • Total Spin   = base_spin × (club_speed / 100)        │
│  • Spin Axis    = (face − path×1.5) × 2.5               │
│                                                         │
│  All base values per-club from tuning.json              │
└────────────────────┬────────────────────────────────────┘
                     │ BallFlight object
                     ▼
┌─────────────────────────────────────────────────────────┐
│              OpenGolfSim TCP API  127.0.0.1:3111        │
│                                                         │
│  Heartbeat (every 0.5 s):                               │
│    {"type":"device","status":"ready"}                   │
│                                                         │
│  Shot payload:                                          │
│    {"type":"shot","shot":{                              │
│       "ballSpeed": <mph>,                               │
│       "verticalLaunchAngle": <deg>,                     │
│       "horizontalLaunchAngle": <deg>,                   │
│       "spinSpeed": <rpm>,                               │
│       "spinAxis": <deg>                                 │
│    }}                                                   │
│                                                         │
│  Inbound (handled):                                     │
│    type=player  → updates active club from API          │
│    type=result  → prints carry/total distances          │
└─────────────────────────────────────────────────────────┘
```

---

## HID Hardware Reference

| Property | Value |
|---|---|
| **Vendor ID (VID)** | `0x0547` |
| **Product ID (PID)** | `0x3294` |
| **Read packet size** | 60 bytes |
| **Write report size** | 61 bytes (Report ID `0x00` + 1 command byte + 59 zero bytes) |
| **Back sensor row** | 8 LEDs, spacing `0.5 in` (12.7 mm); bits in `data[i]` or `data[i+1]` |
| **Front sensor row** | 8 LEDs, same spacing; opcode `0x4A` |
| **Inter-row spacing** | `2.25 in` (57.15 mm) — used for speed calculation |

### Command Bytes

| Constant | Byte | Effect |
|---|---|---|
| `CMD_SENSORS_ON` | `0x50` | Activates sensor array (sent on connect) |
| `CMD_LED_RED` | `0x51` | LED → red (device busy / processing) |
| `CMD_LED_GREEN` | `0x52` | LED → green (ready for next swing) |
| `CMD_SENSORS_OFF` | `0x80` | Deactivates sensors (sent on disconnect) |

---

## Packet Format (60-byte HID Report)

Data arrives as 12 × 5-byte chunks. Each chunk:

```
Offset +0  Back-row sensor bitmask  (bit N = LED N active)
Offset +1  Front-row sensor bitmask
Offset +2  Opcode
Offset +3  Gap high byte  (elapsed ticks, big-endian)
Offset +4  Gap low byte
```

### Opcodes

| Opcode | Meaning |
|---|---|
| `0x81` | Back sensors — initial trigger (back row, first contact) |
| `0x52` | Back sensors — subsequent / timing update |
| `0x4A` | Front sensors — club has crossed front row |

### Speed Formula

```
speed_mph = (SENSOR_SPACING / (elapsed_ticks × 18)) × 2236.94
```

Where `SENSOR_SPACING = 28500` (hardware ticks spanning 57.15 mm between rows).  
The `18` divisor and `2236.94` multiplier are directly inherited from RepliShot's `usbcode.cpp`.

### Ball-Hit Detection

A ball contact is confirmed when:
1. A `0x4A` chunk has `gap > 0x25` — marks a *potential* ball read.
2. The *next* `0x4A` chunk has `gap < 0x20` — confirms ball hit.

On confirmation, elapsed time is back-adjusted by `prev_gap` to strip out the ball-impact delay from the speed calculation.

---

## Physics & Tuning

All per-club constants live in [tuning.json](tuning.json). Edit this file to dial in feel without touching code.

| Key | Description |
|---|---|
| `BallSpeed` | Smash factor multiplier (ball speed ÷ club speed) |
| `VlaLow` / `VlaHigh` | Vertical launch angle range (degrees); average is used as base VLA |
| `BSLow` / `BSHigh` | Back-spin range (rpm); average is scaled by club speed |

**Global keys:**

| Key | Description |
|---|---|
| `SensorSpacing` | Tick count spanning the inter-row distance (calibration) |
| `LedSpacing` | Lateral LED spacing in mm (calibration) |
| `MaxHLA` | Maximum allowed horizontal launch angle (not yet enforced in code) |

### Smash Factor Contact Penalty

Off-center hits (heel/toe) reduce ball speed:

```python
contact_penalty = abs(face_contact) * 0.05
ball_speed = club_speed * (smash - contact_penalty)
```

`face_contact` is the center of the active back-row LED range offset from sensor center (range ≈ −3.5 to +3.5).

---

## Simulation Mode

Activated automatically when no HID device is found, or can be forced by disconnecting hardware.

`simulation.py → generate_simulated_shot(club_name)` synthesizes a valid 60-byte packet by:

1. Picking a random club speed within realistic amateur–tour ranges.
2. Choosing a random spin axis target (−7.5° to +7.5°).
3. Back-solving the required face angle and LED skew to produce that axis.
4. Encoding timing ticks and bitmasks into the packet byte layout.

The resulting packet is structurally identical to hardware output and passes through `ShotProcessor` unchanged — this makes simulation a faithful integration test of the full pipeline.

---

## Technical Gotchas

### 1. `hidapi` wheel is Python-version and arch locked
The bundled `hidapi-0.15.0-cp315-cp315-win_amd64.whl` only installs on CPython 3.15 / Windows x64. This is only required in an air gapped (no internet) environment. Pip install pyusb to avoid this issue.


### 2. Windows USB conflict
A conflict may happen if you run OptiSender and the official OptiShot software at the same time. Two applications cannot hold exclusive access to the same HID device simultaneously. Whichever opens it first wins; the other gets an access denied error.

Practical impact on your program
Scenario	                                Result
OptiSender running, OEM software closed	    Works fine
OEM software running, OptiSender starts	    HID Connection Error → falls into simulation mode
Both started simultaneously	                Race condition — first one to open wins

### 3. Non-blocking reads need a tight poll loop
`device.set_nonblocking(1)` means `device.read(60)` returns `[]` immediately when no data is available. The main loop sleeps only 10 ms between polls (`time.sleep(0.01)`). Do not increase this interval significantly or you risk missing short-duration swing packets.

### 4. Duplicate packet guard is byte-exact
`OptiFilter.is_duplicate` does a full 60-byte equality check. The OptiShot hardware can re-deliver the same packet on subsequent reads before the next swing. If you see shots being silently dropped, verify the filter isn't matching near-identical but distinct packets (this can happen at very low swing speeds where sensor patterns repeat).

### 5. API connection is fire-and-forget with 5-second retry
If OpenGolfSim is not running when OptiSender starts, the program falls back to `simulation_mode=False` hardware mode but simply has no API destination. Shots are processed and printed to console but not transmitted. The retry loop checks every 5 seconds — start OpenGolfSim at any point and the next retry window will connect.


## File Reference

| File | Role |
|---|---|
| [OptiSender.py](OptiSender.py) | Entry point; main loop, API socket management, club cycling |
| [opti_reader.py](opti_reader.py) | HID device open/close, command writes, raw 60-byte reads |
| [data_filters.py](data_filters.py) | Duplicate and validity filters before processing |
| [shot_processor.py](shot_processor.py) | 60-byte packet parser; speed, face angle, path, contact, smash |
| [ballphysics.py](ballphysics.py) | Ball-flight physics engine; reads `tuning.json` |
| [simulation.py](simulation.py) | Synthetic packet generator; mirrors hardware packet layout |
| [tuning.json](tuning.json) | Per-club smash factor, VLA range, spin range, global calibration |
| [api_monitor.py](api_monitor.py) | Standalone API traffic monitor (debugging aid) |
