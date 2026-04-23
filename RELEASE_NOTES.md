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
