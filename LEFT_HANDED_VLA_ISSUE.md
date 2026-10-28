# Left-handed VLA issue: saved for a future update

Saved 2026-10-28. **Fixed on branch `lh-vla-fix`** (see Status below). Found by reading the code; not yet confirmed with a real left-handed swing on the pad.

## Status

- Done on the branch: `calculate_ball_flight(metrics, club, left_handed=False)` flips the launch-angle sign for left-handers; `OptiSender.py` passes `left_handed`; `test_ballphysics.py` covers both hands; right-handed output verified identical (378 Test Data rows).
- Not yet done: a left-handed shot sent to MuniGolf to confirm the displayed VLA; a real left-handed swing on the pad.

## The problem

[ballphysics.py:63-64](ballphysics.py#L63-L64) computes launch angle as `VLA = base VLA + 0.3 x face angle`, where face angle is the **World frame** value (positive = pointing right of the Target Line, same for both hands). The code comment calls it a loft relationship: an open face adds loft.

- **Right-handed:** positive face = Open, so higher launch. Correct direction.
- **Left-handed:** positive face = Closed (see Open / Closed in [CONTEXT.md](CONTEXT.md)). A closed face should lower launch, but the engine raises it. An Open left-handed face lowers launch instead of raising it. Wrong direction.

The engine never receives handedness; it is only used afterwards to name the swing ([swing_labels.py](swing_labels.py)). The Manual Simulation window sliders are also World frame for both hands.

Start direction (HLA) and spin axis follow the World frame and are correct for both hands.

## Size of the error

Small. +/-5 deg face moves VLA by +/-1.5 deg, which moved MuniGolf's carry by about 3 yds on the Driver (194.9 vs 200.9 yds). Note the 0.3 coefficient is itself a rough stand-in for dynamic loft; real launch depends on loft and attack angle, which the pad does not measure.

## Why OptiSender must fix it (MuniGolf will not)

Checked 2026-10-28 in MuniGolf's log and executable strings:
- MuniGolf flies the ball data it is sent (`OnOpenConnectShot` logs only HLA, VLA, speed, spin, spin axis). It rejects a shot with 0 ball speed ("Ignoring shot with 0 ball speed"). No sign it derives ball flight from club path, face angle or handedness.
- It stores and displays club data (club speed, face to target, club path, AOA and dynamic loft show "--" because we do not send them) and derives only simple values (face to path, back/side spin, smash, air time).
- It tells the launch monitor the golfer's hand (`"Handed":"LH"` in the 201 player message) but does not change how it reads ball data. World frame values flew correctly with MuniGolf set to LH (positive HLA = right).
- Not tested: sending club data with 0 ball speed to see exactly how it reacts (expected: ignored).

## Proposed fix

1. Pass handedness into `PhysicsEngine.calculate_ball_flight` (it is already known in OptiSender.py as `left_handed`, and in the Manual Simulation window).
2. Flip the sign of the face-angle term in the VLA calculation for left-handers, so it follows Open / Closed instead of right / left. Leave HLA and spin axis unchanged.
3. Add tests for both hands (and keep the right-handed numbers identical, so SwingData.xlsx Test Data stays valid).
4. Re-run a left-handed shot against MuniGolf (script workflow described in the memory notes) and compare VLA and carry.

## Related

- [TOE_HEEL_RESEARCH.md](TOE_HEEL_RESEARCH.md): gear effect for toe/heel hits, also paused. Both changes touch ballphysics.py, so consider doing them together.
