from fastapi.testclient import TestClient

from sixtyfivekmconvoy.api.app import app


def test_create_and_play_one_choice():
    client = TestClient(app)
    res = client.post("/games", json={"num_players": 3, "human_seat": 0, "seed": 3})
    assert res.status_code == 200
    data = res.json()
    assert "game_id" in data
    legal = data["snapshot"]["legal_actions"]
    assert legal
    res2 = client.post(
        f"/games/{data['game_id']}/choice?seat=0",
        json={"choice": legal[0]},
    )
    assert res2.status_code == 200
    assert "state" in res2.json()


def test_index_served():
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    assert "65km Convoy" in res.text


def test_continue_pause_flow():
    client = TestClient(app)
    res = client.post(
        "/games",
        json={"num_players": 3, "human_seat": 0, "seed": 9, "pause_after_actions": True},
    )
    assert res.status_code == 200
    data = res.json()
    gid = data["game_id"]
    snap = data["snapshot"]
    # May already be awaiting continue after bot prelude, or waiting on human assign
    assert "awaiting_continue" in snap
    assert snap["pause_after_actions"] is True

    # Disable pause and ensure settings endpoint works
    res2 = client.post(
        f"/games/{gid}/settings?seat=0",
        json={"pause_after_actions": False},
    )
    assert res2.status_code == 200
    assert res2.json()["pause_after_actions"] is False

    res3 = client.post(f"/games/{gid}/continue?seat=0")
    assert res3.status_code == 200
