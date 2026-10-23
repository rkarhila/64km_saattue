# 65km Convoy

Pure-Python board-game engine with a **PettingZoo AEC** training surface and a **web UI** (one human + bot opponents).

## Install

```bash
cd dev
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Self-play (random agents)

```bash
convoy-selfplay --players 3 --seed 0 --episodes 5 -o stats.jsonl
# or
python -m sixtyfivekmconvoy.cli.selfplay --players 3 --seed 0 --verbose
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
Terminal rewards use ranking (`+1` … `-1`) by default (`reward_mode="rank"` or `"points"`).

## Web UI (human vs bots)

```bash
convoy-web --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000/
```

API:

- `POST /games` → `{game_id, human_seat, snapshot}`
- `POST /games/{id}/choice?seat=0` with `{"choice": [...]}`
- `WS /games/{id}/ws?seat=0` (same payload)

Sessions keep multiple seats in mind; v1 fills non-human seats with `RandomAgent`.

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
| `src/sixtyfivekmconvoy/agents/` | Random / human bridges |
| `src/sixtyfivekmconvoy/api/` | FastAPI sessions |
| `src/sixtyfivekmconvoy/cli/` | Self-play + terminal |
| `src/sixtyfivekmconvoy/data/cards/` | CSV decks |
| `web/` | Vanilla JS UI |

Legacy socket `server/` / `client/` packages are superseded by this layout.
