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
