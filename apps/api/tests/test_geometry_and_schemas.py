import math

import numpy as np
import pytest
from pydantic import ValidationError

from app.models.events import EventDetails, EventType, MatchEvent
from app.models.simulation import SimulationConfig
from app.simulation import geometry as g


def test_attack_frame_is_an_involution():
    for x, y in [(0, 0), (10.5, 60.2), (105, 68), (52.5, 34)]:
        for d in (1, -1):
            ax, ay = g.to_attack_frame(x, y, d)
            assert g.from_attack_frame(ax, ay, d) == pytest.approx((x, y))
    assert g.to_attack_frame(10, 5, -1) == (95, 63)


def test_array_conversion_matches_scalar():
    pts = np.array([[1.0, 2.0], [100.0, 60.0]])
    conv = g.arr_to_attack_frame(pts, -1)
    assert conv[0].tolist() == list(g.to_attack_frame(1.0, 2.0, -1))
    assert np.allclose(g.vel_to_attack_frame(np.array([[1.0, -2.0]]), -1), [[-1.0, 2.0]])


def test_goal_geometry():
    assert g.distance_to_goal(105 - 11, 34) == pytest.approx(11)
    centre = g.goal_opening_angle(94, 34)
    wide = g.goal_opening_angle(94, 10)
    assert centre > wide > 0
    assert centre == pytest.approx(2 * math.atan(g.GOAL_HALF / 11), rel=1e-6)
    # Symmetric around the centre line.
    assert g.goal_opening_angle(90, 30) == pytest.approx(g.goal_opening_angle(90, 38))
    assert g.in_penalty_area(95, 34) and not g.in_penalty_area(80, 34)


def test_point_segment_distance_and_clamp():
    d, t = g.point_segment_distance(np.array([[5.0, 3.0]]), np.array([0.0, 0.0]), np.array([10.0, 0.0]))
    assert d[0] == pytest.approx(3) and t[0] == pytest.approx(0.5)
    c = g.clamp_to_pitch(np.array([[-5.0, 80.0]]), 0.5)
    assert c.tolist() == [[0.5, 67.5]]


def test_zone_value_increases_towards_goal():
    assert g.zone_value(95, 34) > g.zone_value(80, 34) > g.zone_value(50, 34)


def _event(**kw):
    base = dict(event_id="m-ev-1", match_id="m", seq=1, sim_time_ms=0, match_clock_ms=0,
                event_type=EventType.PASS_ATTEMPTED)
    base.update(kw)
    return MatchEvent(**base)


def test_event_schema_is_strict_and_immutable():
    e = _event(details=EventDetails(pass_length_m=12.0))
    with pytest.raises(ValidationError):
        e.seq = 5  # frozen
    with pytest.raises(ValidationError):
        _event(unknown_field=1)
    with pytest.raises(ValidationError):
        _event(event_type="NOT_A_TYPE")
    assert MatchEvent.model_validate_json(e.model_dump_json()) == e
    assert e.schema_version == "1.0"


def test_simulation_config_bounds():
    with pytest.raises(ValidationError):
        SimulationConfig(rollouts=10_000)
    with pytest.raises(ValidationError):
        SimulationConfig(horizon_s=60)
