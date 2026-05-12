# OptiSender v1.0.0a6 — Release Notes

## What's New since v1.0.0a5

### RH-Only Physics — Handedness is Now Display-Only

The physics engine has been simplified to right-handed conventions throughout. Left-handed mode now affects only how values are **labeled** in the overlay — the underlying ball flight math is identical for both golfers.

- Removed `left_handed` parameter from `PhysicsEngine.calculate_ball_flight()` — LH sign-flip block deleted
- `Ctrl+H` and the simulation window handedness toggle still work, but they control the overlay display labels only
- Deleted `verify_handedness.py` (development diagnostic, no longer needed)

### Overlay LH Label Flipping

When Left-Handed mode is active, the overlay now re-labels sensor values to match the golfer's frame of reference without altering the physics output:

| Metric | RH display | LH display |
|---|---|---|
| Face Angle | Open / Closed as computed | Open ↔ Closed swapped |
| Club Path | `+` = in-to-out | Sign negated (`+` = in-to-out from LH perspective) |
| Face Contact | Toe / Heel as computed | Toe ↔ Heel swapped |

New `_flip_for_lh()` method and `_CONTACT_FLIP` lookup dict added to `overlay_display.py`.

### Manual Simulation — Direct Metrics Injection

The Manual Simulation Window no longer encodes slider values into a synthetic 60-byte HID packet. Instead it builds a metrics dict directly and injects it into the physics engine, bypassing `generate_from_metrics()` and `ShotProcessor` entirely.

**Why this matters:** The HID round-trip introduced LED quantization errors (~26% face angle underread, ±2.3° path bias at zero input) that could not be corrected without physical hardware specifications. Direct injection eliminates these artifacts:

- Face = 0°, Path = 0° now produces exactly 0° HLA and "Straight" shape — no offset
- Face = +5° Open now reaches the physics engine as exactly +5° Open, not ~3.7°
- Path = +10° in-to-out now displays as exactly +10°, not +11.5° or +6.9°

The physical pad pipeline (`ShotProcessor` → `PhysicsEngine`) is completely unchanged. The two paths are mutually exclusive — hardware data always goes through `ShotProcessor`.

**LH sign convention in direct injection:**

| Slider input | RH sensor value | LH sensor value |
|---|---|---|
| Face = +5° Open | `face_angle = −5.0` (sensor inverted) | `face_angle = +5.0` |
| Path = +10° in-to-out | `path_deg = +10.0` | `path_deg = −10.0` |

`Ctrl+Space` / `Ctrl+S` random shots still use the HID packet path (`generate_from_metrics()`) and are unaffected.

### Path Encoding Centroid Fix (`generate_from_metrics`)

The front LED (`f_min`) target in `generate_from_metrics()` was computed relative to an incorrectly centered back LED reference, causing asymmetric path encoding (RH and LH paths of equal magnitude encoded differently). The formula now uses the actual centroid of both back sensor rows (`b_min_A` and `b_min_B`) as the reference point, producing symmetric path encoding for random shot profiles.

### Slider Resolution Updates

Both the Manual Simulation Window and `test.py` manual tester now use 1° steps for all angular sliders:

| Slider | Previous step | New step |
|---|---|---|
| Face Angle | 0.5° | 1.0° |
| Club Path | 0.5° | 1.0° |

---

## Files Changed since v1.0.0a5

| File | Change |
|---|---|
| `ballphysics.py` | Removed `left_handed` parameter; deleted LH sign-flip block |
| `OptiSender.py` | Direct metrics injection branch (`"metrics"` key in sim queue); `left_handed` flag retained for display only; removed `left_handed=` from physics call; simplified contact label (RH-only) |
| `overlay_display.py` | Added `_flip_for_lh()`, `_CONTACT_FLIP`; LH label flipping for face angle, path, and contact |
| `simulation.py` | `_send()` rewritten for direct metrics injection; `generate_from_metrics()` path centroid fix; face and path slider resolution changed to 1.0° |
| `test.py` | Removed LH toggle and `_toggle_handed()`; face and path slider resolution changed to 1.0°; `resolution` parameter added to `_make_slider()` |
| `verify_handedness.py` | Deleted |
| `README.md` | Updated for v1.0.0a6 — manual simulation section, architecture diagram, sign convention note, file reference |

---

# OptiSender v1.0.0a5 — Release Notes

## What's New since v1.0.0a4

### Manual Simulation Window

A new **Manual Simulation Window** opens automatically when no OptiShot hardware is detected, replacing the previous keyboard-only simulation flow. The window provides full control over every shot parameter and feeds exact HID packets through the complete `ShotProcessor → PhysicsEngine → API` pipeline — identical to a real pad reading.

- Opens automatically at startup when no device is found; also opens if the device disconnects mid-session and closes when it reconnects
- **Club Speed, Face Angle, and Club Path sliders** let you specify exact values rather than relying on random shot profiles
- **Club selector** — choose any club independently of the OGS API selection for testing specific clubs
- **Handedness toggle** — color-coded button (orange = RH, blue = LH) synced bidirectionally with `Ctrl+H` and the overlay indicator
- **Send Shot button** — generates a precise HID packet and queues it for processing; disabled during processing to prevent missed shots
- **Ready state indicator** — status line shows `◌ Processing…` after a shot is sent, then `● Ready` once the system is prepared for the next shot
- The window cannot be closed manually — it is controlled entirely by hardware detection state

### Ready State Tied to API Result

The simulation window's ready state is now driven by the actual OpenGolfSim API response rather than a fixed software timer:

- **Primary trigger:** OGS sends a `result` message → ready signalled 5 seconds later (allows the game screen to fully update)
- **Fallback:** If the API is not connected or does not respond, ready fires automatically after 12 seconds — matching the time required for the game engine to cycle
- Prevents shots from being queued before the simulator is ready to receive them, mirroring the green LED behaviour of the physical pad

### Handedness Sign Convention Corrected

A long-standing bug where left-handed ball flight was computed incorrectly has been fixed throughout the pipeline.

- **Root cause:** `ballphysics.py` accepted a `left_handed` parameter but never used it — all LH shots were computed identically to RH shots
- **Fix:** Face angle and club path are now sign-flipped before physics for LH golfers, so the same physical swing produces identical ball flight regardless of handedness
- **Convention:** For both RH and LH, positive face = open (pointing away from the golfer), positive path = in-to-out. The sensor inversion (`encode_face = -face_angle` in `generate_from_metrics`) ensures sim window inputs round-trip correctly through `ShotProcessor`
- Ball flight sent to the OGS API is now correct for both hands

### Simulation Packet Encoding Corrected

`generate_from_metrics()` previously encoded face angle with the wrong sign, causing all simulated shots (including random profiles) to produce opposite-direction ball flight:

- Added `encode_face = -face_angle` to apply the same sensor inversion that real hardware produces
- Random shot profiles (fade, draw, slice, hook) now curve in the correct direction
- `generate_simulated_shot()` refactored to call `generate_from_metrics()` internally — both paths share identical packet-building logic

### Swing Path Display Label Fixed (LH)

Swing path displayed in the overlay and console for left-handed golfers was being negated, showing the inverse of the entered value:

- `eff_path = -path_val if left_handed else path_val` changed to `eff_path = path_val` for both hands
- The sensor and sim encoder preserve the golfer-convention path sign through the round-trip — no display flip is needed
- API output unchanged (was already correct)

### Overlay Display — Swing Speed Slider Removed

The Swing Speed percentage slider previously shown in the overlay during simulation mode has been removed:

- Club speed is now set directly in the Manual Simulation Window slider (mph, not %)
- Overlay window height reduced to match; connection status indicator still shows `◌ Simulation` / `● Connected`

### Handedness Color Coding

RH/LH indicators are now color-coded consistently across all windows:

- **Right-handed:** orange (`#f57c00`) — overlay indicator and sim window button
- **Left-handed:** blue (`#1565c0`) — overlay indicator and sim window button

### Duplicate Shot Filter Bypassed for Manual Simulation

The byte-exact duplicate packet filter (`OptiFilter.is_duplicate`) is now bypassed for shots originating from the Manual Simulation Window:

- Every button press is an intentional shot — blocking identical consecutive packets would prevent re-sending the same parameters
- Hardware pad reads and keyboard-triggered random shots still go through the duplicate filter as before

### README Updated

`README.md` updated to reflect all v1.0.0a5 changes:

- New **Manual Simulation Window** section with full usage guide, controls table, sign convention table, and ready-state documentation
- Overlay Display section updated (swing speed slider removed, handedness color coding documented)
- Simulation Mode section updated to distinguish manual vs. random keyboard trigger
- Technical Gotchas updated from "two Tk windows" to "three Tk windows"
- File Reference entry for `simulation.py` updated

---

## Files Changed since v1.0.0a4

| File | Change |
|---|---|
| `simulation.py` | New `SimulationWindow` class; new `generate_from_metrics()`; `generate_simulated_shot()` refactored to use it; `encode_face = -face_angle` sensor inversion fix; added `import threading` |
| `ballphysics.py` | LH sign flip applied to face angle and path before physics; `left_handed` parameter now used |
| `OptiSender.py` | `SimulationWindow` integration; `sim_packet_queue`; API-driven ready state with 5 s delay and 12 s fallback; `skip_dup_check` for manual sim packets; swing path display negation removed for LH; face label negation unified for both hands; `import threading` added |
| `overlay_display.py` | Swing speed slider removed; `get_speed_pct()` removed; window height reduced to 560; handedness label now color-switches between orange (RH) and blue (LH) |
| `README.md` | Manual Simulation Window section added; overlay and simulation sections updated; gotcha #4 updated |

---

# OptiSender v1.0.0a4 — Release Notes

## What's New since v1.0.0a3

### Tuning Editor
A new floating Tuning Editor window lets you adjust all ball flight parameters at runtime without restarting OptiSender.

- Open with **Ctrl+T** or the **Tuning** button on the overlay window
- **Global parameters:** Speed Calibration and Face Compression affect all clubs
- **Per-club parameters:** Ball Speed (smash factor), Launch Angle (Vla), and Base Spin (BS) adjustable per club via dropdown
- Sliders populate from the current `tuning.json` every time the window opens
- **Save** writes to `tuning.json` and reloads the physics engine live — no restart needed
- **Cancel** reverts all sliders to the last saved state and closes the window
- **Revert to Defaults** restores factory defaults from `tuning_default.json`
- Unsaved-change guard: closing with unsaved changes presents a Save & Close / Cancel Changes dialog with no plain dismiss
- Window is draggable and stays on top of other applications

### Face Angle Compression (tanh model)
A new non-linear face angle compression model reduces the effect of erratic face angle readings from the OptiShot pad while preserving accuracy on small, realistic angles.

- Uses `eff_face = k × tanh(face_angle / k)` to dampen extreme readings
- Compression level is tunable in the Tuning Editor as a 0–100% slider
  - **0%** — k=200, compression is negligible (realistic, full face influence)
  - **50%** — k=15 (default), ±30° face reduced ~50% laterally
  - **100%** — k≈0, near-perfectly straight regardless of face angle
- Raw face angle still used for vertical launch angle; only horizontal launch and spin axis are compressed

### Tuning Simplified to Single Vla / BS per Club
`tuning.json` previously stored `VlaLow`/`VlaHigh` and `BSLow`/`BSHigh` pairs. These have been collapsed to single `Vla` and `BS` values per club, reducing complexity and making tuning more predictable.

- `ballphysics.py` updated to read `Vla` and `BS` directly
- `tuning_default.json` added as a factory-defaults reference file (not modified by the Tuning Editor)
- All existing club entries migrated to the new single-value format

### Face Angle Sign Convention (Trackman)
Face angle sign convention now matches Trackman throughout the pipeline:
- **Positive** = open (pointing right for RH, pointing left for LH)
- **Negative** = closed

`shot_processor.py` negates the raw hardware value to align with this convention. `simulation.py` encodes shot profiles using Trackman-convention values, which are then negated before HID encoding so they decode correctly after processing.

### Left-Handed Support Improvements
- Face angle, swing path, spin axis, and face contact labels all correctly flip for left-handed players
- Toe/heel contact labels physically reversed for LH (sensor geometry is mirrored)
- Overlay handedness indicator updated in real time

### Overlay Display Updates
- **Tuning** button added to the overlay — opens the Tuning Editor window
- Overlay now accepts `sim_input` dict reference, allowing the Tuning button to signal the main loop
- `schedule_ui()` helper added to safely post callables onto the Tk thread from any thread

### README Rewrite
`README.md` fully rewritten to reflect all current features:
- GitHub Releases download link for the pre-built executable at the top of Installation
- Installation split into Option A (executable) and Option B (source/developers)
- New Overlay Display and Tuning Editor sections with detailed descriptions
- Updated keyboard controls table including Ctrl+T
- Updated Data Flow Architecture with current formulas (tanh compression, single Vla/BS)
- Updated Physics & Tuning Reference and File Reference

---

## Files Changed since v1.0.0a3

| File | Change |
|---|---|
| `tuning_editor.py` | New — floating Tuning Editor window (Toplevel in overlay's Tk thread) |
| `tuning_default.json` | New — factory-default tuning values, never modified at runtime |
| `overlay_display.py` | Added Tuning button, `schedule_ui()`, `sim_input` integration |
| `ballphysics.py` | tanh face compression, single Vla/BS per club, LH sign handling |
| `shot_processor.py` | Face angle negated to Trackman convention |
| `simulation.py` | Profiles in Trackman convention, encode_face negated before HID encoding |
| `OptiSender.py` | TuningEditor integration, Ctrl+T, physics reload, LH label fixes |
| `tuning.json` | Simplified to single Vla/BS, added FaceCompression section |
| `README.md` | Full rewrite — current features, tuning guide, architecture |

---

# OptiSender v1.0.0a3 — Release Notes

## What's New since v1.0.0a2

### OGS API Updated to Event-Driven Model
`api_monitor.py` has been refactored to match the updated OpenGolfSim API, which now pushes events server-side rather than requiring client polling.

- Removed fake shot heartbeat — no more phantom shots sent every 5 seconds to stimulate a response
- `select` timeout increased from 0.1 s to 30 s; the thread now sleeps until data arrives instead of spinning 10× per second
- Structured display formatters for all three event types: `player` (club change), `shot result` (carry/total/roll/height/lateral), `device status`
- Stale `status == 200` suppression filter removed — all received messages are now displayed
- Connection logic extracted into a clean `connect()` helper

### Club Selection Now Driven by OGS API
Manual keyboard club cycling (Ctrl+↑ / Ctrl+↓) has been disabled. Club selection is now received exclusively through the OpenGolfSim API `player` event, keeping the in-game club and OptiSender in sync automatically.

### Simulation Speed Ranges Adjusted for Mid-Handicap Amateur
`CLUB_SPEED_RANGES` in `simulation.py` have been scaled down from tour/scratch levels to realistic mid-handicap amateur values (driver ~75–90 mph vs. the previous 93–115 mph). All clubs and putter updated proportionally.

### PyInstaller Build Script
`build.bat` added for building a standalone Windows executable using PyInstaller in `--onedir` (folder) mode.

- UPX disabled (`--noupx`) — UPX-packed binaries are commonly flagged as malware by AV engines
- Onedir output reduces AV heuristic triggers vs. single-file self-extracting bundles
- Unused stdlib modules excluded to reduce binary footprint
- `cd /d "%~dp0"` ensures the script works when double-clicked from Explorer on any drive
- `pause` on both success and failure paths so the window stays open for output
- `build.bat` added to `.gitignore`

---

## Files Changed since v1.0.0a2

| File | Change |
|---|---|
| `api_monitor.py` | Full refactor — event-driven, no heartbeat, structured event display |
| `OptiSender.py` | Manual club cycling (Ctrl+↑/↓) commented out; club from API only |
| `simulation.py` | `CLUB_SPEED_RANGES` reduced to mid-handicap amateur values |
| `build.bat` | New — PyInstaller onedir build script |
| `.gitignore` | Added `build.bat` |

---

# OptiSender v1.0.0a2 — Release Notes

## What's New since v1.0.0a1

### Overlay Display Window
A new floating, movable heads-up display shows real-time club metrics after each shot without needing to watch the console.

- Displays club name, ball detected (yes/no), and handedness (Left/Right)
- Shows shot metrics: club speed, ball speed, launch angle, spin, HLA, and VLA
- Window is draggable and stays on top of other applications
- Connection status indicator shows whether the OptiShot device is live or in simulation mode

### Ball Detection Toggle
- Press **`b`** to toggle ball detection on/off at runtime — useful for testing or forcing simulation shots without repositioning a ball

### Bug Fixes
- **Spin axis bug fixed** — spin axis sign was inverted, causing draw/fade spin to be reported backwards to the API
- **Connection status** now correctly reflects live USB vs. simulation mode in the overlay

---

## Files Changed since v1.0.0a1

| File | Change |
|---|---|
| `overlay_display.py` | New — floating overlay window with club metrics and connection status |
| `OptiSender.py` | Ball toggle keybind, overlay integration, connection status tracking |
| `ballphysics.py` | Spin axis sign fix |
| `shot_processor.py` | Spin axis correction, overlay data passing |
| `opti_reader.py` | Connection status reporting |
| `tuning.json` | Tuning value updates |

---

# OptiSender v1.0.0a1 — Release Notes

## What's New

### Simulation Mode Overhaul
The simulation engine has been completely rewritten to produce packets that are physically accurate end-to-end — the synthetic 60-byte HID packet now passes through `ShotProcessor` and `PhysicsEngine` with correct decoded values rather than approximate ones.

- **Fixed sensor constants** — `SENSOR_SPACING` and `LED_SPACING` now match `shot_processor.py` exactly, correcting a bug where simulated club speeds were decoded ~10× out of range
- **7 named shot profiles** with weighted random selection: Straight, Fade, Draw, Slice, Hook, Toe hit, Heel hit
- **Club-aware packet generation** — every club in `tuning.json` produces appropriate speeds, contact zones, and face angles; was previously hardcoded to Driver for all clubs
- **Shot profile printed on trigger** — console shows profile name, club, and speed for each simulated swing

### Physics & Tuning
- `tuning.json` expanded to cover all clubs including `3I`, `4I`, and `Putter`
- `CLUB_SPEED_RANGES` in `simulation.py` updated to include `3I`, `4I`, and `Putter` speed ranges

### USB / HID
- `opti_reader.py` updated to use the `hid` PyPI package (`pip install hid`) instead of the bundled ABI-locked `.whl` — compatible with any Python version and architecture without rebuilding
- Bundled `hidapi-0.15.0-cp315-cp315-win_amd64.whl` is no longer required

### Architecture
- Codebase split into focused single-responsibility modules: `opti_reader.py`, `shot_processor.py`, `data_filters.py`, `ballphysics.py`, `simulation.py`
- `README.md` added with full data-flow architecture diagram, packet format reference, tuning guide, and documented technical gotchas

---

## Installation

```bash
pip install hid pynput
python OptiSender.py
```

> On Windows, if the OptiShot 2 is not detected the program automatically enters simulation mode — no hardware required for development or testing.

---

## Known Limitations

- Club ID mappings from the OpenGolfSim API (`DR`, `PT`, `AW`, `UW`) are partially hardcoded; clubs not in the explicit map pass through verbatim and must match internal club names exactly
- `MaxHLA` in `tuning.json` is defined but not yet enforced in the physics engine
- Running OptiSender alongside the official OptiShot software will cause an HID access conflict — only one application can hold the device at a time

---

## Files Changed

| File | Change |
|---|---|
| `simulation.py` | Full rewrite — correct constants, shot profiles, club-aware packets |
| `opti_reader.py` | Switched from bundled hidapi wheel to `pip install hid` |
| `ballphysics.py` | Minor read path fixes for tuning.json |
| `tuning.json` | Added `3I`, `4I`, `Putter` entries |
| `OptiSender.py` | Club cycling, API club ID mapping, heartbeat loop |
| `shot_processor.py` | Ported from RepliShot C++ (`shotprocessing.cpp`) |
| `data_filters.py` | Duplicate guard and validity filter |
| `README.md` | New — full project documentation |
