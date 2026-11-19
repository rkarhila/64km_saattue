"""Queue-card faces are a fixed vector, not a catalog id."""

from __future__ import annotations

import numpy as np
import pytest

from sixtyfivekmconvoy.env.card_features import (
    CARD_FEAT_DIM,
    F_AMBUSH,
    F_ATK_G,
    F_ATK_R,
    F_ATK_S,
    F_ATROCITIES,
    F_ATROCITY_THRESHOLD,
    F_CASH,
    F_COUNTER,
    F_DESTROY_CASH,
    F_DISCARD,
    F_DRUNK_ATROCITIES,
    F_DURABILITY,
    F_FAIL_HIT,
    F_FROM_RESISTANCE,
    F_HIDDEN,
    F_HIT,
    F_INTOXICATE,
    F_LOOT,
    F_MIN_PLAYERS,
    F_PRESENT,
    F_REL_FRONT,
    F_REORDER,
    F_RES_LOOT,
    F_SLOT,
    F_TYPE_MAULING,
    F_TYPE_P,
    F_TYPE_PILLAGE,
    F_TYPE_RESISTANCE,
    F_WHICH,
    F_WHOLE_ZONE,
    F_ZONE_A,
    F_ZONE_B,
    encode_card_block,
    encode_queue,
    encode_slot,
    printed_card_features,
)


def _face(kind: str, card_id: int) -> np.ndarray:
    return np.asarray(printed_card_features(kind, card_id), dtype=np.float32)


def test_mauling_faces_keep_target_and_attack_and_drop_other_decks():
    ground = _face("mauling", 27)
    assert ground[F_PRESENT] == 1.0
    assert ground[F_TYPE_MAULING] == 1.0
    assert ground[F_ZONE_A] == 1.0
    assert ground[F_WHOLE_ZONE] == 0.0
    assert ground[F_REL_FRONT] == pytest.approx(1 / 6)
    assert ground[F_HIT] == pytest.approx(0.1)
    assert ground[F_ATK_G] == 1.0
    assert ground[F_FROM_RESISTANCE] == 0.0
    assert ground[27:].sum() == 0.0

    sabotage = _face("mauling", 12)
    assert sabotage[F_WHICH] == pytest.approx(1.0)
    assert sabotage[F_TYPE_P] == 1.0
    assert sabotage[F_HIT] == pytest.approx(0.3)
    assert sabotage[F_DISCARD] == pytest.approx(0.5)
    assert sabotage[F_FAIL_HIT] == pytest.approx(0.3)
    assert sabotage[F_ATK_S] == 1.0
    assert sabotage[F_ATROCITY_THRESHOLD] == pytest.approx(0.2)
    assert sabotage[27:].sum() == 0.0

    # The stored category on an R card is a placeholder, not the drawn deck.
    resistance_hit = _face("mauling", 75)
    assert resistance_hit[F_ZONE_A] == 1.0
    assert resistance_hit[F_REL_FRONT] == pytest.approx(1 / 6)
    assert resistance_hit[F_HIT] == 0.0
    assert resistance_hit[F_FROM_RESISTANCE] == 1.0
    assert resistance_hit[F_ATK_R] == 1.0
    assert resistance_hit[27:].sum() == 0.0


def test_resistance_faces_use_the_ambush_target_only():
    reorder = _face("resistance", 1)
    assert reorder[F_TYPE_RESISTANCE] == 1.0
    assert reorder[F_ZONE_A] == 1.0
    assert reorder[F_ZONE_B] == 1.0
    assert reorder[F_WHOLE_ZONE] == 1.0
    assert reorder[F_REL_FRONT] == 0.0
    assert reorder[F_REORDER] == 1.0
    assert reorder[F_AMBUSH] == 0.0
    assert reorder[F_COUNTER] == pytest.approx(0.1)
    assert reorder[F_RES_LOOT] == pytest.approx(1 / 6)
    assert reorder[F_DURABILITY] == pytest.approx(1 / 12)
    assert reorder[F_DESTROY_CASH] == pytest.approx(0.25)
    assert reorder[F_MIN_PLAYERS] == pytest.approx(2 / 5)
    assert reorder[18:27].sum() == 0.0
    assert reorder[35:].sum() == 0.0

    ambush = _face("resistance", 8)
    assert ambush[F_ZONE_A] == 1.0
    assert ambush[F_REL_FRONT] == pytest.approx(1 / 6)
    assert ambush[F_AMBUSH] == pytest.approx(0.3)
    assert ambush[F_REORDER] == 0.0
    assert ambush[F_RES_LOOT] == pytest.approx(0.5)
    assert ambush[F_DURABILITY] == pytest.approx(2 / 12)
    assert ambush[18:27].sum() == 0.0
    assert ambush[35:].sum() == 0.0


def test_pillage_face_is_only_the_reward():
    looted = _face("pillage", 15)
    assert looted[F_TYPE_PILLAGE] == 1.0
    assert looted[F_CASH] == pytest.approx(2 / 5)
    assert looted[F_LOOT] == pytest.approx(1 / 5)
    assert looted[F_DRUNK_ATROCITIES] == 1.0
    assert looted[F_ATROCITIES] == 0.0
    assert looted[F_INTOXICATE] == 0.0
    assert looted[6:35].sum() == 0.0

    drunk = _face("pillage", 9)
    assert drunk[F_CASH] == pytest.approx(1 / 5)
    assert drunk[F_INTOXICATE] == 1.0
    assert drunk[F_DRUNK_ATROCITIES] == 1.0
    assert drunk[F_LOOT] == 0.0
    assert drunk[6:35].sum() == 0.0


def test_hidden_slot_keeps_type_and_position_only():
    hidden = encode_slot("mauling", 27, visible=False, slot=2)
    assert hidden[F_PRESENT] == 1.0
    assert hidden[F_HIDDEN] == 1.0
    assert hidden[F_TYPE_MAULING] == 1.0
    assert hidden[F_SLOT] == pytest.approx(2 / 5)
    assert hidden[6:].sum() == 0.0
    assert hidden.shape == (CARD_FEAT_DIM,)

    queue = encode_queue("pillage", [(15, True)])
    assert queue.shape == (8, CARD_FEAT_DIM)
    assert queue[0, F_PRESENT] == 1.0
    assert queue[0, F_SLOT] == 0.0
    assert queue[1:].sum() == 0.0


def test_observation_card_block_matches_on_both_paths():
    from sixtyfivekmconvoy.core.engine import GameEngine
    from sixtyfivekmconvoy.env.spaces import card_block_slice, fill_observation, flatten_observation

    engine = GameEngine()
    engine.reset(num_players=2, seed=1)
    engine.resistance_queue.cards_and_visibilities.clear()
    engine.pillage_queue.cards_and_visibilities.clear()
    engine.mauling_queue.cards_and_visibilities.clear()
    engine.resistance_queue.put_card(1, visible=True)
    engine.pillage_queue.put_card(15, visible=True)
    engine.mauling_queue.put_card(27, visible=True)
    engine.mauling_queue.put_card(12, visible=False)
    expected = encode_card_block(
        {
            "resistance": [(1, True)],
            "pillage": [(15, True)],
            "mauling": [(27, True), (None, False)],
        }
    )
    fast = fill_observation(engine, 0, 2)
    slow = flatten_observation(engine.observe("player_0"), 0, 2)
    start, end = card_block_slice(fast.shape[0])
    assert end - start == expected.size
    assert np.allclose(fast[start:end], expected.reshape(-1))
    assert np.allclose(slow[start:end], expected.reshape(-1))
    assert np.allclose(fast, slow)


def test_card_token_forward_pass():
    torch = pytest.importorskip("torch")
    from sixtyfivekmconvoy.env.spaces import card_block_slice, observation_size
    from sixtyfivekmconvoy.rl.policy import MaskedActorCritic

    dim = observation_size(3)
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
    model.eval()
    obs = np.zeros(dim, dtype=np.float32)
    start, _end = card_block_slice(dim)
    obs[start + F_PRESENT] = 1.0
    obs[start + F_TYPE_RESISTANCE] = 1.0
    obs[start + F_REORDER] = 1.0
    mask = np.zeros(256, dtype=np.float32)
    mask[0] = 1
    flat, logp, value, picks, _vec = model.act(obs, mask, deterministic=True)
    assert flat in (0, -1)
    assert isinstance(logp, float) and isinstance(value, float)
    assert picks
    assert not any(isinstance(m, torch.nn.LSTM) for m in model.modules())
