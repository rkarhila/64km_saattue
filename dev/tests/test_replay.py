from fastapi.testclient import TestClient
from sixtyfivekmconvoy.api.app import app


def test_serialize_and_replay():
    client = TestClient(app)

    # 1. Start a game
    res = client.post(
        "/games",
        json={
            "num_players": 3,
            "human_seat": 0,
            "seed": 42,
            "pause_after_actions": True,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "game_id" in data
    snap1 = data["snapshot"]
    assert "shareable_state" in snap1

    # 2. Make some choices
    curr_snap = snap1
    gid = data["game_id"]
    for _ in range(3):
        # If awaiting continue, click continue first
        if curr_snap.get("awaiting_continue"):
            res_cont = client.post(f"/games/{gid}/continue?seat=0")
            assert res_cont.status_code == 200
            curr_snap = res_cont.json()

        legal = curr_snap.get("legal_actions")
        if not legal:
            break

        # Pick the first legal action
        res_choice = client.post(
            f"/games/{gid}/choice?seat=0",
            json={"choice": legal[0]},
        )
        assert res_choice.status_code == 200
        curr_snap = res_choice.json()

    # Get the shareable state from the latest state
    state_str = curr_snap["shareable_state"]
    assert state_str

    # 3. Import the game on a new session
    res_import = client.post("/games/import", json={"state": state_str})
    assert res_import.status_code == 200
    imported_data = res_import.json()
    imported_snap = imported_data["snapshot"]

    # 4. Assert both states are structurally identical
    # Compare round, stage, awaiting_continue, pause_after_actions, and terminal
    assert imported_snap["state"]["round"] == curr_snap["state"]["round"]
    assert imported_snap["state"]["stage"] == curr_snap["state"]["stage"]
    assert imported_snap["awaiting_continue"] == curr_snap["awaiting_continue"]
    assert imported_snap["pause_after_actions"] == curr_snap["pause_after_actions"]
    assert imported_snap["terminal"] == curr_snap["terminal"]

    # Compare players list
    p_curr = curr_snap["state"]["players"]
    p_imp = imported_snap["state"]["players"]
    assert len(p_curr) == len(p_imp)
    for pc, pi in zip(p_curr, p_imp):
        assert pc["number"] == pi["number"]
        assert pc["total_cash"] == pi["total_cash"]
        assert pc["card_count"] == pi["card_count"]

    # Compare convoy units list
    c_curr = curr_snap["state"]["convoy"]
    c_imp = imported_snap["state"]["convoy"]
    assert len(c_curr) == len(c_imp)
    for uc, ui in zip(c_curr, c_imp):
        assert uc["unit_type"] == ui["unit_type"]
        assert uc["tiredness"] == ui["tiredness"]
        assert uc["atrocities"] == ui["atrocities"]
        assert uc["carry"] == ui["carry"]

    # Compare queue counts
    assert imported_snap["state"]["decks"]["queues"] == curr_snap["state"]["decks"]["queues"]
