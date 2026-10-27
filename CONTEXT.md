# OptiSender

Turns what an OptiShot pad measures about a golf swing into ball flight, and shows the swing back to the golfer in their own terms.

## Language

### Frames of reference

**Target Line**:
The line from the ball to the target, viewed from behind the golfer looking toward the target. Every direction in this project is measured against it.
_Avoid_: Aim line, centerline

**World frame**:
Directions measured against the **Target Line**, where positive is right of the line and negative is left. Identical for every golfer.
_Avoid_: Absolute frame, physics frame

**Golfer frame**:
The same directions named from the golfer's own point of view, so the words depend on **Handedness**. Used only when showing results to the golfer.
_Avoid_: Player frame, display frame

**Handedness**:
Whether the golfer swings right-handed (RH) or left-handed (LH). It changes how a swing is named, never how the ball flies.
_Avoid_: Dexterity, side

### Swing measurements

**Face Angle**:
The direction the clubface points at impact, as a **World frame** value: positive points right of the **Target Line**, negative points left.
_Avoid_: Face, clubface angle, sensor face angle

**Club Path**:
The direction the clubhead is travelling at impact, as a **World frame** value: positive heads right of the **Target Line**, negative heads left. A heading, not a position or a sweep across the body.
_Avoid_: Swing path, path angle, "moving left to right"

**Face Contact**:
Where along the clubface the ball was struck, from the heel to the toe. The toe is the end of the clubhead farthest from the golfer and the heel the end nearest. The pad reports a side of the clubface, and **Handedness** decides which side is the toe.
_Avoid_: Strike location, hit location, contact point

**Face-to-Path**:
**Face Angle** minus **Club Path**. This difference, not either value alone, decides how much the ball curves.
_Avoid_: Face-to-path difference

### Golfer-frame names

**Open / Closed**:
The **Golfer frame** names for **Face Angle**. For an RH golfer, positive is Open and negative is Closed; for an LH golfer, positive is Closed and negative is Open. Within 0.5° of the **Target Line** the face is Square for either hand.
_Avoid_: Left/right face

**In-to-Out / Out-to-In**:
The **Golfer frame** names for **Club Path**. For an RH golfer, positive is In-to-Out and negative is Out-to-In; for an LH golfer, positive is Out-to-In and negative is In-to-Out. Within 0.5° of the **Target Line** the path is Neutral for either hand.
_Avoid_: Inside/Out, InOut, OutIn, positive/negative path, On Plane, Straight (for path)

**Shot Shape**:
The **Golfer frame** name for how the ball curves: Straight, Fade, Slice, Draw or Hook. For an RH golfer Fade and Slice curve left-to-right and Draw and Hook curve right-to-left; for an LH golfer it is the reverse. Slice and Hook are the stronger curves.
_Avoid_: Ball flight shape, curve direction

## Relationships

- **Face Angle** and **Club Path** are the swing measurements that decide ball flight; they are always **World frame** values.
- **Shot Shape** follows from **Face-to-Path**, named in the **Golfer frame**.
- **Handedness** only chooses between the two columns of **Open / Closed** and **In-to-Out / Out-to-In**, and which end of the clubface is the toe; it never changes a **World frame** value.

## Example dialogue

> **Dev:** The pad says the **Club Path** is positive. Is that In-to-Out?
> **Domain expert:** Positive means the clubhead is heading right of the **Target Line**. For a right-handed golfer that's In-to-Out. For a left-handed golfer the same heading is Out-to-In.
> **Dev:** So the ball starts the same way for both?
> **Domain expert:** Yes, same **World frame** numbers, same ball flight. Only the words shown to the golfer differ.
> **Dev:** And a **Face Angle** of +3?
> **Domain expert:** Pointing right of the line: Open for the right-hander, Closed for the left-hander.

## Flagged ambiguities

- "Positive face angle" or "positive path" was used for three different values (the raw pad reading, the **World frame** value, and a golfer-frame slider). Resolved: unqualified **Face Angle** and **Club Path** always mean the **World frame** value.
- "Club moving left to right" was used for **Club Path**. Resolved: Club Path is the heading at impact relative to the **Target Line**, not a left-to-right sweep.
