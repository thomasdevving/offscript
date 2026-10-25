import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from app.config import REPO_ROOT, Settings

    s = Settings(agent_mode="policy", use_analysis_cache=False, data_dir=tmp_path_factory.mktemp("data"),
                 scenarios_dir=REPO_ROOT / "scenarios", default_rollouts=100)
    app = create_app(s, preload=["shoot_vs_pass", "risky_through_ball"])
    with TestClient(app) as c:
        yield c


def _wait(client, analysis_id, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        a = client.get(f"/api/analyses/{analysis_id}").json()
        if a["status"] not in ("pending", "running"):
            return a
        time.sleep(0.2)
    raise AssertionError("analysis did not finish")


def test_health_and_listing(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["agent_mode"] == "policy"
    matches = client.get("/api/matches").json()
    assert {m["match_id"] for m in matches} == {"demo-match-073", "demo-match-031"}
    sc = client.get("/api/scenarios").json()
    assert any(s["scenario_id"] == "shoot_vs_pass" and s["decision_count"] for s in sc)
    st = client.post("/api/scenarios/shoot_vs_pass/start").json()
    assert st["match_id"] == "demo-match-073" and st["websocket"].startswith("/ws/")
    assert client.post("/api/scenarios/nope/start").status_code == 404


def test_match_data_endpoints(client):
    info = client.get("/api/matches/demo-match-073").json()
    assert info["home"]["name"] == "Harbour City FC"
    ev = client.get("/api/matches/demo-match-073/events").json()
    assert ev and all(e["event_type"] not in ("PLAYER_POSITION_UPDATED",) for e in ev)
    shots = client.get("/api/matches/demo-match-073/events?types=SHOT_ATTEMPTED").json()
    assert all(e["event_type"] == "SHOT_ATTEMPTED" for e in shots)
    frames = client.get("/api/matches/demo-match-073/frames?step=5").json()
    assert frames and len(frames[0]["players"]) == 22
    jsonl = client.get("/api/matches/demo-match-073/events.jsonl").text.strip().splitlines()
    assert len(jsonl) >= len(ev)
    state = client.get("/api/matches/demo-match-073/state?t_ms=2000").json()
    assert state["sim_time_ms"] <= 2000
    assert client.get("/api/matches/unknown").status_code == 404


def test_analysis_lifecycle(client):
    decisions = client.get("/api/matches/demo-match-073/decisions").json()
    dp = decisions[0]
    snap = client.get(f"/api/decisions/{dp['decision_point_id']}/snapshot").json()
    assert snap["snapshot_id"] == dp["snapshot_id"]
    r = client.post(f"/api/decisions/{dp['decision_point_id']}/analyze", json={"rollouts": 100})
    assert r.status_code == 202 and r.json()["status"] in ("pending", "running", "verified")
    a = _wait(client, r.json()["analysis_id"])
    assert a["status"] == "verified"
    aid = a["analysis_id"]
    res = client.get(f"/api/analyses/{aid}/results").json()
    assert res["status"] == "completed" and len(res["results"]) == len(a["candidates"])
    wfs = client.get(f"/api/analyses/{aid}/workflow").json()
    assert wfs["workflow_status"] == "completed" and wfs["steps"]
    ov = client.get(f"/api/analyses/{aid}/overlays").json()
    assert {o["viewer_mode"] for o in ov} == {"casual", "analyst", "broadcaster"}
    assert all(o["verification_status"] in ("verified", "verified_with_warnings") for o in ov)
    evid = client.get(f"/api/analyses/{aid}/evidence").json()
    assert any(e["ref"] == "sim.rollouts" for e in evid)
    alt = a["candidates"][1]["action_id"]
    traj = client.get(f"/api/analyses/{aid}/trajectories/{alt}").json()
    assert traj["kind"] == "simulated" and traj["frames"]
    traj3 = client.get(f"/api/analyses/{aid}/trajectories/{alt}?rollout=3").json()
    assert traj3["rollout_index"] == 3
    assert client.get(f"/api/analyses/{aid}/trajectories/nope").status_code == 404
    job = client.post(f"/api/analyses/{aid}/simulate", json={"rollouts": 40}).json()
    for _ in range(100):
        j = client.get(f"/api/simulations/{job['simulation_run_id']}").json()
        if j["status"] not in ("pending", "running"):
            break
        time.sleep(0.1)
    assert j["status"] == "completed"
    all_ov = client.get("/api/matches/demo-match-073/overlays?viewer_mode=casual&language=nl").json()
    assert all(o["viewer_mode"] == "casual" and o["language"] == "nl" for o in all_ov)


def test_recap(client):
    assert client.get("/api/matches/demo-match-031/recap").status_code == 404
    rec = client.post("/api/matches/demo-match-031/recap?language=nl").json()
    assert rec["language"] == "nl" and rec["casual"]["story"] and rec["analyst"]["story"]
    assert rec["referenced_event_ids"]
    assert client.get("/api/matches/demo-match-031/recap?language=nl").json()["recap_id"] == rec["recap_id"]


def test_input_validation(client):
    dp = client.get("/api/matches/demo-match-073/decisions").json()[0]["decision_point_id"]
    assert client.post(f"/api/decisions/{dp}/analyze", json={"rollouts": 100000}).status_code == 422
    assert client.post(f"/api/decisions/{dp}/analyze", json={"fault_injection": ["rm -rf"]}).status_code == 422
    assert client.post("/api/decisions/nope/analyze", json={}).status_code == 404
    first = client.get("/api/matches/demo-match-073/events").json()[0]["event_id"]
    assert client.post(f"/api/matches/demo-match-073/events/{first}/decision").status_code == 422


def test_manual_decision(client):
    ev = client.get("/api/matches/demo-match-073/events?types=PASS_ATTEMPTED").json()[-1]
    dp = client.post(f"/api/matches/demo-match-073/events/{ev['event_id']}/decision")
    assert dp.status_code == 201 and dp.json()["source"] == "manual"


def test_websocket_stream(client):
    with client.websocket_connect("/ws/matches/demo-match-073?auto_analyze=false") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["duration_ms"] > 0
        assert ws.receive_json()["type"] == "reset"
        ws.send_json({"type": "speed", "value": 8})
        ws.send_json({"type": "play"})
        seen, frames = set(), 0
        for _ in range(80):
            m = ws.receive_json()
            seen.add(m["type"])
            if m["type"] == "tick":
                frames += len(m["frames"])
            if "decision_detected" in seen and frames > 20:
                break
        assert "tick" in seen and frames > 0
        ws.send_json({"type": "seek", "t_ms": 0})
        for _ in range(20):
            m = ws.receive_json()
            if m["type"] == "reset":
                assert m["t_ms"] == 0
                break


def test_metrics_endpoint(client):
    m = client.get("/api/metrics").json()
    assert "startup.generate_match" in m and m["startup.generate_match"]["count"] >= 2


def test_add_language_narratives(client):
    """Spanish, French and German narratives are added instantly to a finished analysis and all pass verification."""
    for match_id in ("demo-match-073", "demo-match-031"):
        decisions = client.get(f"/api/matches/{match_id}/decisions").json()
        for dp in decisions:
            a = _wait(client, client.post(f"/api/decisions/{dp['decision_point_id']}/analyze").json()["analysis_id"])
            assert a["status"] == "verified"
            for lang in ("es", "fr", "de"):
                out = client.post(f"/api/analyses/{a['analysis_id']}/narratives", params={"language": lang}).json()
                got = [n for n in out["narratives"] if n["language"] == lang]
                assert {n["audience"] for n in got} == {"casual", "analyst", "broadcaster"}, (lang, dp["actor_name"])
                assert all(n["verification_status"] == "verified" for n in got)
    assert client.post("/api/analyses/x/narratives", params={"language": "es"}).status_code == 404
    assert client.post("/api/analyses/x/narratives", params={"language": "xx"}).status_code == 422
