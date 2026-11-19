"""The visible table is in the observation: faces, chips, formation, events."""

from __future__ import annotations

import numpy as np
import pytest

from sixtyfivekmconvoy.core.cards import OFFICER_CATALOG
from sixtyfivekmconvoy.core.engine import GameEngine
from sixtyfivekmconvoy.core.models import Unit, UnitType
from sixtyfivekmconvoy.env.spaces import (
    MAX_OPTIONS,
    MAX_PLAYERS,
    OPTION_FEAT_DIM,
    fill_observation,
    flatten_observation,
    observation_size,
    option_block_slices,
    token_layout,
    token_tail_width,
)
from sixtyfivekmconvoy.env.table_features import (
    CARD_TOKEN_DIM,
    F_COST_A,
    F_COST_T,
    F_COST_U,
    F_MOD,
    F_TANY,
    F_TI,
    F_TIRE,
    F_TL,
    F_TP,
    F_ZA,
    F_ZB,
    F_ZE,
    FACE_DIM,
    FACE_SLOTS,
    N_ACTIONS,
    FORMATION_SEATS,
    H_HIDDEN,
    H_ID,
    H_PRESENT,
    H_STACK,
    HEADER_DIM,
    HIT_PILES,
    O_ACT,
    O_DISCARD,
    O_PASSIVE,
    O_TI,
    O_TIRE,
    O_TL,
    O_TP,
    O_ZA,
    OPTION_TROOP_AT,
    OPTION_UNIT_AT,
    PLAYER_FEAT,
    RESISTANCE_FEAT,
    UNIT_FEAT,
    encode_card_token,
    encode_officer,
    hand_tokens,
)
from sixtyfivekmconvoy.rl.events import (
    EVENT_ACTION,
    EVENT_CASH,
    EVENT_DAMAGE,
    EVENT_REVEAL,
)


def test_action_card_faces_and_hidden_back():
    token = encode_card_token(present=True, visible=True, card_id=0, stack=0)
    attack = token[HEADER_DIM : HEADER_DIM + FACE_DIM]
    patrol = token[HEADER_DIM + FACE_DIM : HEADER_DIM + 2 * FACE_DIM]
    service = token[HEADER_DIM + 2 * FACE_DIM : HEADER_DIM + 3 * FACE_DIM]
    assert attack[0] == 1.0
    assert attack[F_ZA] == 1.0 and attack[F_ZB] == 1.0 and attack[F_ZE] == 0.0
    assert attack[F_TP] == 1.0 and attack[F_TANY] == 0.0
    assert attack[F_MOD] == pytest.approx(0.2)
    assert attack[F_COST_T] == pytest.approx(0.5)
    assert attack[F_COST_U] == pytest.approx(0.5)
    assert attack[F_COST_A] == 0.0
    assert attack[F_TIRE] == 1.0
    assert patrol[7] == 1.0
    assert patrol[F_ZA] == patrol[F_ZB] == patrol[F_ZE] == 1.0
    assert patrol[F_COST_A] == pytest.approx(0.5)
    assert service[14] == 1.0
    assert service[F_TL] == 1.0

    hidden = encode_card_token(present=True, visible=False, card_id=0, stack=1)
    assert hidden[H_PRESENT] == 1.0
    assert hidden[H_HIDDEN] == 1.0
    assert hidden[H_STACK] == pytest.approx(0.5)
    assert hidden[H_ID] == 0.0
    assert hidden[HEADER_DIM:].sum() == 0.0

    own = encode_card_token(present=True, visible=True, card_id=0, stack=0)
    assert np.allclose(own, hand_tokens([0], 1)[0])


def test_officer_passive_and_discard_are_different_vectors():
    passive = encode_officer(
        OFFICER_CATALOG[1].describe(), present=True, visible=True, slot=0
    )
    discard = encode_officer(
        OFFICER_CATALOG[6].describe(), present=True, visible=True, slot=0
    )
    assert passive[O_PASSIVE + 1] == 1.0
    assert passive[O_TP] == 1.0 and passive[O_TI] == 1.0 and passive[O_TL] == 0.0
    assert passive[O_DISCARD:O_DISCARD + 4].sum() == 0.0
    assert discard[O_DISCARD] == 1.0
    assert discard[O_TI] == 1.0 and discard[O_TP] == 0.0
    assert discard[O_ZA] == 1.0
    assert discard[O_ACT] == pytest.approx(18 / N_ACTIONS)
    assert discard[O_TIRE] == 1.0
    assert passive[O_ACT] == 0.0

    token = encode_card_token(
        present=True,
        visible=True,
        card_id=0,
        stack=0,
        officer_face=OFFICER_CATALOG[6].get_discard_action_description(),
    )
    officer_at = HEADER_DIM + (FACE_SLOTS - 1) * FACE_DIM
    extra = token[officer_at : officer_at + FACE_DIM]
    assert extra[18] == 1.0
    assert extra[F_ZA] == 1.0
    assert extra[F_TI] == 1.0
    assert extra[F_TIRE] == 1.0
    plain = encode_card_token(present=True, visible=True, card_id=0, stack=0)
    assert plain[HEADER_DIM + 3 * FACE_DIM :].sum() == 0.0


def test_markers_defence_and_hidden_enemy_order():
    engine = GameEngine()
    engine.reset(num_players=2, seed=1)
    unit = Unit(engine.players[1], UnitType.INFANTRY)
    unit.convoy = engine.convoy
    unit.engine = engine
    unit.actioncard = [0]
    unit.actiontaken = [None]
    unit.action_resolution = [None]
    unit.defending = "G"
    unit.damage_markers = [
        {"damage": 2, "category": 3},
        {"damage": 4, "category": 5},
    ]
    engine.convoy.units = [unit]

    enemy = fill_observation(engine, 0, 2)
    owner = fill_observation(engine, 1, 2)
    assert np.allclose(enemy, flatten_observation(engine.observe("player_0"), 0, 2))
    assert np.allclose(owner, flatten_observation(engine.observe("player_1"), 1, 2))

    unit_at = MAX_PLAYERS + 3 + RESISTANCE_FEAT + HIT_PILES + FORMATION_SEATS
    unit_at += MAX_PLAYERS * PLAYER_FEAT
    row = enemy[unit_at : unit_at + UNIT_FEAT]
    assert row[11 + "ABCE".index(unit.zone())] == 1.0
    assert row[16] == 1.0  # ground defence
    assert row[18] == pytest.approx(0.2)
    assert row[19] == pytest.approx(0.4)
    assert row[22] == pytest.approx(0.3)
    assert row[23] == pytest.approx(0.5)
    assert row[26] == pytest.approx(0.5)
    assert row[27] == 1.0 and row[28] == 0.0

    stacks = token_layout(enemy.shape[0])[3][0]
    hidden = enemy[stacks : stacks + CARD_TOKEN_DIM]
    assert hidden[H_PRESENT] == 1.0 and hidden[H_HIDDEN] == 1.0
    assert hidden[H_ID] == 0.0 and hidden[HEADER_DIM:].sum() == 0.0
    shown = owner[stacks : stacks + CARD_TOKEN_DIM]
    assert np.allclose(shown, hand_tokens([0], 1)[0])

    unit.officers = [OFFICER_CATALOG[6]]
    owner = fill_observation(engine, 1, 2)
    assert np.allclose(owner, flatten_observation(engine.observe("player_1"), 1, 2))
    shown = owner[stacks : stacks + CARD_TOKEN_DIM]
    officer_at = HEADER_DIM + (FACE_SLOTS - 1) * FACE_DIM
    extra = shown[officer_at : officer_at + FACE_DIM]
    assert extra[18] == 1.0
    enemy = fill_observation(engine, 0, 2)
    hidden = enemy[stacks : stacks + CARD_TOKEN_DIM]
    assert hidden[HEADER_DIM:].sum() == 0.0


def test_formation_and_placement_options_use_the_viewer_frame():
    engine = GameEngine()
    engine.reset(num_players=3, seed=4)
    pattern = list(engine.setup_pattern)
    assert pattern
    form_at = MAX_PLAYERS + 3 + RESISTANCE_FEAT + HIT_PILES
    for seat in range(3):
        vec = fill_observation(engine, seat, 3)
        for i, owner in enumerate(pattern):
            rel = (int(owner) - seat) % 3
            assert vec[form_at + i] == pytest.approx((rel + 1) / 6.0)
            if int(owner) == seat:
                assert vec[form_at + i] == pytest.approx(1 / 6)
        assert vec[form_at + len(pattern) : form_at + FORMATION_SEATS].sum() == 0.0

    viewer = int(engine._pending.player_id.split("_")[1])
    vec = fill_observation(engine, viewer, 3)
    start, end, _, _ = option_block_slices(vec.shape[0])
    feats = vec[start:end].reshape(MAX_OPTIONS, OPTION_FEAT_DIM)
    # Option 0 is IPL: infantry, panzer, logistics on the three owned seats.
    assert feats[0, OPTION_TROOP_AT + 1] == 1.0
    assert feats[0, OPTION_TROOP_AT + 3] == 1.0
    assert feats[0, OPTION_TROOP_AT + 8] == 1.0
    assert feats[0, OPTION_TROOP_AT] == 0.0
    assert feats[5, 0] == 1.0
    assert feats[6, 0] == 0.0
    assert int(engine.pending_choice().num_choices) == 1


def test_assign_option_names_the_unit_and_each_face():
    from sixtyfivekmconvoy.core.constants import ChoiceType

    engine = GameEngine()
    engine.reset(num_players=2, seed=3)
    while engine.pending_choice().choicetype == ChoiceType.PLACE_UNITS:
        engine.step([0])
    pending = engine.pending_choice()
    assert pending.choicetype == ChoiceType.CHOOSE_CARD
    assert len(engine.players[0].action_cards) == 5
    unit = pending.payload["assign_unit"]
    viewer = int(pending.player_id.split("_")[1])
    vec = fill_observation(engine, viewer, 2)
    start, end, _, _ = option_block_slices(vec.shape[0])
    feats = vec[start:end].reshape(MAX_OPTIONS, OPTION_FEAT_DIM)
    troop = {"panzer": 0, "infantry": 1, "logistics": 2}[unit["unit_type"]]
    assert feats[0, OPTION_UNIT_AT + troop] == 1.0
    assert feats[0, OPTION_UNIT_AT + 3 + "ABCE".index(unit["zone"])] == 1.0
    assert feats[0, OPTION_UNIT_AT + 7] == pytest.approx(unit["place"] / 14)
    faces = pending.payload["assign_faces"][str(pending.options[0])]
    for i, row in enumerate(faces):
        assert feats[0, OPTION_UNIT_AT + 8 + i * 2] == row[0]
        assert feats[0, OPTION_UNIT_AT + 8 + i * 2 + 1] == row[1]
    assert any(bit == 1 for row in faces for bit in row)


def test_frustration_reveal_and_damage_append_event_rows():
    engine = GameEngine()
    engine.reset(num_players=2, seed=2)
    engine.players[0].get_cash(4, source="test")
    cash = list(engine.event_rows)[-1]
    assert cash[0] == EVENT_CASH and cash[7] == 4

    unit = Unit(engine.players[0], UnitType.INFANTRY)
    unit.convoy = engine.convoy
    unit.engine = engine
    engine.convoy.units = [unit]
    engine.attach_damage_marker(unit, 3, category=1)
    damage = list(engine.event_rows)[-1]
    assert damage[0] == EVENT_DAMAGE
    assert damage[4] == 0 and damage[7] == 3 and damage[8] == 0

    engine._broadcast(
        "frustrated",
        event_type=EVENT_ACTION,
        actor=0,
        target=0,
        card_id=4,
        card_visible=True,
        amount=-1,
    )
    frustrated = list(engine.event_rows)[-1]
    assert frustrated[0] == EVENT_ACTION
    assert frustrated[4] == 0 and frustrated[7] == -1 and frustrated[8] == 1

    from sixtyfivekmconvoy.core import actions as action_mod

    engine.pause_after_actions = False
    engine.pillage_queue.cards_and_visibilities.clear()
    engine.mauling_queue.cards_and_visibilities.clear()
    engine.resistance_queue.cards_and_visibilities = [[1, False]]
    gen = action_mod.resolve_scout(engine, unit, count=1)
    try:
        next(gen)
    except StopIteration:
        pass
    reveals = [row for row in engine.event_rows if row[0] == EVENT_REVEAL]
    assert reveals
    assert reveals[-1][5] == 2  # resistance queue code
    assert reveals[-1][6] == 1 and reveals[-1][8] == 1


def test_mlp_reads_the_board_prefix_only():
    torch = pytest.importorskip("torch")
    from sixtyfivekmconvoy.rl.policy import MaskedActorCritic

    dim = observation_size(3)
    assert observation_size(2) == observation_size(5) == dim
    model = MaskedActorCritic(
        obs_dim=dim,
        hidden=32,
        n_layers=1,
        width=32,
        d_model=32,
        nhead=4,
        dim_feedforward=64,
        tf_layers=1,
    )
    assert model.encoder[0].in_features == model.board_dim
    assert model.board_dim == dim - token_tail_width()
    assert model.board_dim < dim
    obs = np.zeros(dim, dtype=np.float32)
    hand_at = token_layout(dim)[2][0]
    obs[hand_at + H_PRESENT] = 1.0
    mask = np.zeros(256, dtype=np.float32)
    mask[0] = 1.0
    flat, logp, value, picks, _vec = model.act(obs, mask, deterministic=True)
    assert flat in (0, -1)
    assert isinstance(logp, float) and isinstance(value, float)
    assert picks
    assert not any(isinstance(module, torch.nn.LSTM) for module in model.modules())
