"""
Golfer-frame labels for a swing (terms defined in CONTEXT.md).

ShotProcessor and PhysicsEngine work in the world frame: positive is right of the
target line for both hands. Handedness only changes the names shown to the golfer,
so every label the console and overlay display is built here, once.
"""

LABEL_BAND = 0.5  # degrees either side of the target line shown as Square / Neutral


def world_face(metrics):
    # Raw pad face angle has the opposite sign to the world frame (same negation as PhysicsEngine).
    return -metrics['face_angle']


def face_label(metrics, left_handed):
    face = world_face(metrics)
    if abs(face) <= LABEL_BAND:
        name = "Square"
    elif (face > 0) != left_handed:
        name = "Open"
    else:
        name = "Closed"
    return f"{name} {abs(face):.1f}°"


def path_label(metrics, left_handed):
    path = metrics['path_deg']
    if abs(path) <= LABEL_BAND:
        name = "Neutral"
    elif (path > 0) != left_handed:
        name = "In-to-Out"
    else:
        name = "Out-to-In"
    return f"{name} {abs(path):.1f}°"


def contact_label(metrics, left_handed):
    # Sensor index 0 is the pad end nearest a right-handed golfer (heel) and 7 the far end (toe).
    # A left-handed golfer stands at the other end, so mirror the indices first.
    # Mapping inferred from RepliShot's face/path signs and pad layout, not yet confirmed on a pad.
    lo, hi = metrics['raw_min_back'], metrics['raw_max_back']
    if left_handed:
        lo, hi = 7 - hi, 7 - lo
    if hi == 0:   return "Missed"
    if hi <= 2:   return "Far Heel"
    if hi == 3:   return "Heel"
    if lo >= 5:   return "Far Toe"
    if lo == 4:   return "Toe"
    return "Center"


def shot_shape_label(ball, left_handed):
    # Spin axis is world frame (positive curves right). Right curve = fade/slice for RH, draw/hook for LH.
    curve = -ball.spin_axis if left_handed else ball.spin_axis
    if curve > 10:   return "Slice"
    if curve > 3:    return "Fade"
    if curve > -3:   return "Straight"
    if curve > -10:  return "Draw"
    return "Hook"


def describe_swing(metrics, ball, left_handed):
    """Golfer-frame label strings keyed the way the overlay expects."""
    return {
        "face_angle":   face_label(metrics, left_handed),
        "swing_path":   path_label(metrics, left_handed),
        "face_contact": contact_label(metrics, left_handed),
        "shot_shape":   shot_shape_label(ball, left_handed),
    }
