import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from app.config import REPO_ROOT, Settings

    s = Settings(agent_mode="policy", use_analysis_cache=False, data_dir=tmp_path_factory.mktemp("mvdata"),
                 scenarios_dir=REPO_ROOT / "scenarios", multiverse_cell_rollouts=30, multiverse_max_cell_rollouts=30)
    with TestClient(create_app(s, preload=["shoot_vs_pass"])) as c:
        yield c


def _wait_job(client, job_id, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/multiverse/jobs/{job_id}").json()
        if j["status"] not in ("pending", "running"):
            return j
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_multiverse_api_flow(client):
    dp = client.get("/api/matches/demo-match-073/decisions").json()[0]
    r = client.post("/api/multiverse/sessions", json={"decision_point_id": dp["decision_point_id"]})
    assert r.status_code == 201
    sess = r.json()
    root = sess["root_node_id"]
    tree = client.get(f"/api/multiverse/sessions/{sess['session_id']}/tree").json()
    assert {n["kind"] for n in tree["nodes"]} == {"root", "observed"}
    opts = client.get(f"/api/multiverse/branches/{root}/options").json()
    assert opts["options"] and opts["actual"]["is_actual"]
    v = client.post(f"/api/multiverse/branches/{root}/validate", json={"action_type": "pass", "target_player_id": "A05"})
    assert v.json()["ok"] is False and v.json()["code"] == "OPPONENT_TARGET"
    bad = client.post(f"/api/multiverse/branches/{root}/actions", json={"action": {"action_type": "pass",
                                                                                  "target_player_id": "H14"}})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "TARGET_UNAVAILABLE"
    job = client.post(f"/api/multiverse/branches/{root}/actions",
                      json={"action": {"action_type": "pass", "target_player_id": "H07"}})
    assert job.status_code == 202
    j = _wait_job(client, job.json()["job_id"])
    assert j["status"] == "completed" and j["child_node_id"]
    child = j["child_node_id"]
    node = client.get(f"/api/multiverse/branches/{child}").json()
    assert node["entering_action_source"] == "user" and node["parent_node_id"] == root
    state = client.get(f"/api/multiverse/branches/{root}/state").json()
    assert state["snapshot_id"] == dp["snapshot_id"]
    traj = client.get(f"/api/multiverse/branches/{child}/trajectory").json()
    assert traj["frames"] and traj["simulated"] is True and traj["boundaries"]
    an = client.get(f"/api/multiverse/branches/{child}/analysis").json()
    assert an["status"] == "completed" and an["matrix"] and an["summary"]["defensive_counter_id"]
    ag = client.get(f"/api/multiverse/branches/{child}/agents").json()
    assert {"attacking_agent", "defending_agent"} <= {s["agent"] for s in ag["steps"]}
    cmp = client.post("/api/multiverse/compare", json={"node_a": child, "node_b": f"{sess['session_id']}~observed"})
    assert cmp.status_code == 200 and cmp.json()["explanation"]
    assert client.get("/api/multiverse/sessions/nope").status_code == 404
    assert client.post(f"/api/multiverse/branches/{root}/actions", json={"action": {}}).status_code == 422
    with client.websocket_connect(f"/ws/multiverse/{sess['session_id']}") as ws:
        assert ws.receive_json()["type"] == "hello"
    # the canonical match is untouched
    assert client.get("/api/matches/demo-match-073/decisions").json()[0]["snapshot_id"] == dp["snapshot_id"]
