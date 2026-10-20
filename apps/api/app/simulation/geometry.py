"""Pitch geometry in physical metres.

World coordinates: x in [0, 105] along the touchline, y in [0, 68] across the pitch.
The home team attacks towards increasing x in the first half and towards decreasing x
in the second half.

The simulator works internally in an *attack frame*: the attacking team always attacks
towards x = 105. Converting between world and attack frame is a 180 degree rotation
about the centre spot (an involution), which preserves handedness (left stays left
from the attacker's point of view).
"""

from __future__ import annotations

import math

import numpy as np

PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0
CENTRE = (PITCH_LENGTH / 2, PITCH_WIDTH / 2)
GOAL_WIDTH = 7.32
GOAL_HALF = GOAL_WIDTH / 2
GOAL_Y_MIN = PITCH_WIDTH / 2 - GOAL_HALF
GOAL_Y_MAX = PITCH_WIDTH / 2 + GOAL_HALF
PENALTY_AREA_DEPTH = 16.5
PENALTY_AREA_HALF_WIDTH = 20.16
SIX_YARD_DEPTH = 5.5
PENALTY_SPOT_DIST = 11.0

# Attack-frame goal the attacking team shoots at.
ATTACK_GOAL = np.array([PITCH_LENGTH, PITCH_WIDTH / 2])
OWN_GOAL = np.array([0.0, PITCH_WIDTH / 2])


def to_attack_frame(x: float, y: float, direction: int) -> tuple[float, float]:
    """Convert world coordinates to the attack frame of a team attacking in `direction` (+1/-1)."""
    if direction == 1:
        return x, y
    return PITCH_LENGTH - x, PITCH_WIDTH - y


def from_attack_frame(x: float, y: float, direction: int) -> tuple[float, float]:
    # The rotation is its own inverse.
    return to_attack_frame(x, y, direction)


def arr_to_attack_frame(xy: np.ndarray, direction: int) -> np.ndarray:
    if direction == 1:
        return xy.copy()
    out = np.empty_like(xy)
    out[..., 0] = PITCH_LENGTH - xy[..., 0]
    out[..., 1] = PITCH_WIDTH - xy[..., 1]
    return out


def vel_to_attack_frame(v: np.ndarray, direction: int) -> np.ndarray:
    return v.copy() if direction == 1 else -v


def distance(a: tuple[float, float] | np.ndarray, b: tuple[float, float] | np.ndarray) -> float:
    return float(math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1])))


def distance_to_goal(x: float, y: float) -> float:
    """Distance (attack frame) from (x, y) to the centre of the attacked goal."""
    return float(math.hypot(PITCH_LENGTH - x, PITCH_WIDTH / 2 - y))


def goal_opening_angle(x: float, y: float) -> float:
    """Angle (radians) subtended by the goal mouth from (x, y) in the attack frame."""
    a1 = math.atan2(GOAL_Y_MIN - y, PITCH_LENGTH - x)
    a2 = math.atan2(GOAL_Y_MAX - y, PITCH_LENGTH - x)
    ang = abs(a2 - a1)
    if x >= PITCH_LENGTH:
        return 0.0
    return float(ang)


def in_bounds(x: float, y: float, margin: float = 0.0) -> bool:
    return -margin <= x <= PITCH_LENGTH + margin and -margin <= y <= PITCH_WIDTH + margin


def clamp_to_pitch(xy: np.ndarray, margin: float = 0.5) -> np.ndarray:
    out = np.array(xy, dtype=float, copy=True)
    np.minimum(np.maximum(out[..., 0], margin, out=out[..., 0]), PITCH_LENGTH - margin, out=out[..., 0])
    np.minimum(np.maximum(out[..., 1], margin, out=out[..., 1]), PITCH_WIDTH - margin, out=out[..., 1])
    return out


def in_penalty_area(x: float, y: float) -> bool:
    return x >= PITCH_LENGTH - PENALTY_AREA_DEPTH and abs(y - PITCH_WIDTH / 2) <= PENALTY_AREA_HALF_WIDTH


def point_segment_distance(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Distance from point(s) `p` (..., 2) to segment a-b and the segment parameter t in [0, 1]."""
    ab = b - a
    denom = float(ab @ ab)
    if denom < 1e-9:
        d = np.linalg.norm(p - a, axis=-1)
        return d, np.zeros_like(d)
    t = np.clip(((p - a) @ ab) / denom, 0.0, 1.0)
    proj = a + t[..., None] * ab
    return np.linalg.norm(p - proj, axis=-1), t


def unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n < 1e-9:
        return np.zeros(2)
    return v / n


def rotate(v: np.ndarray, angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.array([c * v[0] - s * v[1], s * v[0] + c * v[1]])


def zone_value(x: float, y: float) -> float:
    """Simple attacking-position value proxy in [0, ~0.4] (attack frame).

    This is a transparent heuristic, *not* a fitted expected-threat (xT) model: it decays
    with distance to goal and rewards central positions with a wide goal angle. It is used
    only to steer in-rollout teammate decisions and to rank candidate actions.
    """
    d = distance_to_goal(x, y)
    ang = goal_opening_angle(x, y)
    return float(0.42 * math.exp(-d / 11.0) * (0.35 + 0.65 * min(1.0, ang / 0.7)) + 0.004 * max(0.0, x - 40) / 65)
