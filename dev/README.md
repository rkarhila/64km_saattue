# 65km Convoy

Pure-Python board-game engine with a **PettingZoo AEC** training surface and a **web UI** (one human + bot opponents).

## Install

```bash
cd dev
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

`[dev]` includes the server and the PettingZoo env. The game itself installs
with only NumPy. Add `[web]` to run `convoy-web`, `[env]` for the training
environment, and `[rl]` for PyTorch.

## Self-play (random agents)

```bash
convoy-selfplay --players 3 --seed 0 --episodes 5 -o stats.jsonl
# or
python -m sixtyfivekmconvoy.cli.selfplay --players 3 --seed 0 --verbose
```

## RL training (self-play + bot league)

Install the optional torch extra, then train a **transformer** PPO policy
into a **league** of versioned / branchable bots. Full walkthrough:
**[docs/rl-training.md](docs/rl-training.md)**. A 4-hour GPU run of the
1050-sized network is `PYTHONPATH=src python scripts/train_4h.py` from `dev/`.

```bash
pip install -e ".[rl]"
# Prefer CPU torch if you do not need CUDA:
# pip install torch --index-url https://download.pytorch.org/whl/cpu

convoy-train --league runs/league --name main --players 3 --timesteps 50000 \
  --width 128 --num-envs 8 --minibatch-size 256
convoy-league --league runs/league list
convoy-league --league runs/league branch <id> --name aggressive
convoy-train --league runs/league --from <id> --branch-as aggressive --timesteps 20000
convoy-league --league runs/league eval aggressive --episodes 20
```

## PettingZoo env

```python
from sixtyfivekmconvoy.env.convoy_env import ConvoyEnv

env = ConvoyEnv(num_players=3, seed=0)
env.reset(seed=0)
agent = env.agent_selection
obs = env.observe(agent)
legal = env.infos[agent]["legal_actions"]
env.step(0)  # index into legal_actions
```

Action = index into `infos[agent]["legal_actions"]` (also mirrored in `action_mask`).  
Default RL reward (`reward_mode="win"`): +1 for finishing 1st, plus step proxies for promotion points and cash (see [docs/rl-training.md](docs/rl-training.md)).

## Web UI (human vs bots)

```bash
convoy-web --host 127.0.0.1 --port 8000 --password salasana
# open http://127.0.0.1:8000/
# --password defaults to 1234 when omitted
```

API:

- `POST /games` → `{game_id, human_seat, snapshot}`
- `POST /games/{id}/choice?seat=0` with `{"choice": [...]}`
- `WS /games/{id}/ws?seat=0` (same payload)

Lobby: choose **Satunnaiset botit** or a **League-RL** checkpoint (from
`runs/league` or `CONVOY_LEAGUE`). Non-human seats share that policy.

## One player in the browser

The same page can run without FastAPI. A static server rooted at `dev/` lets
the browser fetch this package; Pyodide runs `play.LocalLobby`, and the other
seats are random bots. The trained policy is not loaded in the browser yet.

```bash
cd dev
PYTHONPATH=src python -m sixtyfivekmconvoy.play
```

Open http://127.0.0.1:8000/web/local.html. The password is still 1234. The
first load downloads Pyodide and NumPy. With no `?version=` the page loads
`versions/alpha_01`, whose `config.py` matches the `retire` profile and whose
`cards/` are that version's own copy. `?version=dev` loads `versions/dev`.
The checkpoint `curriculum-step1840496` is in the opponent list when
`versions/alpha_01/bots/curriculum-step1840496/` is present. It was trained on
the Alpha 01 cards. A checkpoint stores its own `config.py` and `cards/`, and
the lobby warns if the version's files have changed since that copy. Random
bots remain available.

The Python server chooses its version at startup:

```bash
convoy-web --version alpha_01
```

Training with `CONVOY_VERSION=alpha_01` (or `convoy-train --version alpha_01`)
writes new checkpoints into that version's `bots/` folder.

## Terminal human vs bots

```bash
convoy-terminal --players 3 --seed 1 --human-seat 0
```

## Tests

```bash
pytest
```

## Layout

| Path | Role |
|------|------|
| `src/sixtyfivekmconvoy/core/` | Pure engine (no I/O) |
| `src/sixtyfivekmconvoy/env/` | PettingZoo `AECEnv` |
| `src/sixtyfivekmconvoy/rl/` | Recurrent PPO self-play, league checkpoints, branching |
| `src/sixtyfivekmconvoy/agents/` | Random / human / RL bridges |
| `src/sixtyfivekmconvoy/api/` | FastAPI sessions |
| `src/sixtyfivekmconvoy/cli/` | Self-play, train, league, terminal |
| `src/sixtyfivekmconvoy/data/cards/` | CSV decks used when no version is selected |
| `versions/` | One directory per playable version (`config.py` and `cards/`) |
| `web/` | Vanilla JS UI |

Legacy socket `server/` / `client/` packages are superseded by this layout.
