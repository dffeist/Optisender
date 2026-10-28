# Toe and Heel hits: research notes

Saved 2026-10-28 so this can be picked up later. Nothing here has been implemented in OptiSender.

## Where things stand

- **Engine today** ([ballphysics.py](ballphysics.py)): contact only lowers ball speed, by `|contact| x 0.03` of smash factor. Toe and Heel give identical results. There is no start-direction, spin or spin-axis change (no gear effect).
- **Contact value** ([shot_processor.py](shot_processor.py)): `(min_back + max_back) / 2 - 3.5`. Heel = pad index 3 (contact -0.5), Center = indices 3 to 4 (0.0), Toe = index 4 (+0.5). Labels are in [swing_labels.py](swing_labels.py) (Far Heel <= index 2, Far Toe >= index 5).
- **Sent to MuniGolf:** only ball and club data. MuniGolf is never sent the contact, so any toe/heel effect must be baked into ball speed, VLA, HLA, spin and spin axis before sending.
- **Test data:** SwingData.xlsx (Driver, 7 Iron and SW sheets) covers Center contact only. The Toe/Heel rows in the Test Data sheet are identical by design. The user chose "Center only for now".

## Pad geometry (inferred from the code, not published)

No published diagram or spec with sensor measurements was found (searched retailer pages, forum threads, patents). Known outside facts: 2 rows of infrared sensors, 16 sensors total (so 8 per row), unit about 9.75" W x 14.5" L x 1.375" H (one retailer listing, source page not confirmed).

The code constants give the geometry. In shot_processor.py, `SENSOR_SPACING = 185` and `LED_SPACING = 15`. Evidence they are millimeters:
- The speed formula `185 / (elapsed * 18) * 2236.94 * 1.10` only gives correct mph if distance is in mm and time in microseconds (1 mm/us = 2236.94 mph). A 90 mph swing covers 185 mm in about 4.6 ms.
- The path angle is `atan2(LED delta, SENSOR_SPACING)`, so both constants share a unit.

| Measurement | Value |
|---|---|
| LED pitch (heel to toe) | 15 mm (about 0.59") |
| 8 LEDs, first to last | 105 mm (about 4.1") |
| Distance between the two rows | 185 mm (about 7.3") |

Consequence: one index step is about 0.59". Heel (index 3) and Toe (index 4) are only about **0.3" off center**. Far Heel/Far Toe (index 2 / 5) are about 0.9" off. The ends (index 0 / 7) are about 2.1" off.

To confirm: measure LED pitch on the physical pad with a ruler.

## What a real toe or heel hit does (Driver, 90 mph, face 0, path 0, right-handed)

These are ESTIMATES from the sources below plus gear-effect physics. The sources give directions and a few data points, not per-inch rpm or degree figures.

| | Center | Toe (about 0.5-1" off) | Heel (about 0.5-1" off) |
|---|---|---|---|
| Ball speed | 127.8 mph (smash 1.42) | about 2-6% lower | about 2-7% lower, usually worse than toe |
| Start direction | 0 deg | slightly right, about 0.5-2 deg | slightly left, about 0.5-2 deg |
| Spin axis | 0 deg | draw/hook, about 4-15 deg | fade/slice, about 4-15 deg |
| Total spin | 3275 rpm | similar or a bit lower | often higher, sometimes much higher |
| Carry effect | baseline | about -5 yds average | about -18 yds average |

At the pad's real 0.3" Toe/Heel, expect the low end: about 1-2% speed loss (the engine's 1.5% smash drop is close) and only a degree or two of spin axis. The big effects belong to Far Toe/Far Heel (0.9" and beyond).

Data points behind the table:
- MyGolfSpy Labs horizontal impact study: heel strikes started farthest left with a fade-type spin axis and lost about 18 yds on average; toe strikes started farthest right with a draw-type axis and lost just over 5 yds.
- Golf Digest robot testing: toe misses at about 3/4" cost about 5 yds; some drivers lost 25-35 yds on low-heel strikes.
- Golf Australia, one Trackman comparison: a heel strike lost about 10 mph ball speed at similar club speed and spin nearly doubled.
- A small high-school experiment (1" off center, 30 trials per group) found no smash factor difference between toe and heel; weight it lightly (tiny, not launch-monitor based).

## Status 2026-10-28: gear effect built, off by default

Implemented as the conservative tiered model recommended below (dead band at Heel/Toe, modest effect at the Far readings, capped beyond, club-scaled) behind a Tuning editor slider **Gear Effect (toe/heel)** that defaults to 0 (off). Direction is mirrored for left-handers using the same index convention as `swing_labels.contact_label`. Still to do: confirm the heel/toe direction on the physical pad, measure how much center strikes scatter in contact index, then raise the slider. See RELEASE_NOTES.md and README.md ("Gear Effect"). The original ideas list follows.

## Ideas for when we come back

1. Add a gear-effect model to the engine: speed loss, start direction (HLA), spin axis and spin scaled by contact in inches (0.59" per index step), for woods much more than irons (gear effect is small on irons).
2. Check the pad's LED pitch with a ruler first.
3. Send Toe/Heel shots to MuniGolf (the same way as the Center tests) and add them to the Driver/7 Iron/SW sheets.
4. Related open item: VLA uses `0.3 x` world-frame face angle, which is backwards for a left-handed golfer (a closed face should lower launch). Saved separately in [LEFT_HANDED_VLA_ISSUE.md](LEFT_HANDED_VLA_ISSUE.md); not fixed.

## Sources

- [Golf Digest: driver robot testing, mishit locations](https://www.golfdigest.com/story/driver-analysis-robot-testing-mishit-locations)
- [Golf Digest: 2026 drivers robotic testing data](https://www.golfdigest.com/story/drivers-2026-robotic-testing-data-gear-questions)
- [MyGolfSpy Labs: horizontal impact location study](https://mygolfspy.com/labs/mgs-labs-horizontal-impact-study/)
- [Plugged In Golf: Ball Flight Laws #5, gear effect](https://pluggedingolf.com/?p=3994)
- [Physics Question #2419 (science.ca)](https://science.ca/askascientist/viewquestion.php?qID=2419)
- [Golf Australia (PressReader): causes of a slice](https://www.pressreader.com/australia/golf-australia/20190101/282604558921508)
- [High-school study: off-center hits, smash factor and dispersion](https://wcskids.net/mmstc/students/research/physics/2013/ford-jhons.asp)
- [Golf Simulator Forum: Straight shots in OptiShot (2 rows of IR sensors)](https://golfsimulatorforum.com/forum/optishot/262100-straight-shots-in-optishot)
- [Golf Simulator Forum: OptiShot tips (pad height)](https://golfsimulatorforum.com/forum/optishot/67718-optishot-tips)
