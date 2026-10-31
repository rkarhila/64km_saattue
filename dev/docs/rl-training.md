# RL self-play & bot league

Train a PPO policy that plays 65km Convoy against itself and against frozen
checkpoints. Checkpoints live in a **league** directory with parent lineage so
you can fork distinct bots for playtesting.

## Install

```bash
cd dev
pip install -e ".[rl]"
```

Torch is an optional extra (`rl`). CPU works for a first pass.

## Quick start

```bash
# 1) Train a main lineage
convoy-train --league runs/league --name main --players 3 --timesteps 50000

# 2) List checkpoints (copy an id for branching)
convoy-league --league runs/league list

# 3a) Fork only (copy weights, no training)
convoy-league --league runs/league branch <id> --name aggressive

# 3b) Or fork and keep training the branch
convoy-train --league runs/league --from <id> --branch-as aggressive --timesteps 20000

# 4) Smoke-eval vs random opponents
convoy-league --league runs/league eval aggressive --episodes 20

# 5) Tag / export for playtesting
convoy-league --league runs/league promote aggressive --tag playtest
convoy-league --league runs/league export aggressive -o bots/playtest.pt
```

## Command reference

### `convoy-train`

Runs PPO self-play and writes checkpoints into `--league`.

| Flag | Meaning |
|------|---------|
| `--league DIR` | League root (`league.json` + `checkpoints/`) |
| `--name NAME` | Learner lineage name (used in checkpoint names) |
| `--players N` | Seats per game (default 3) |
| `--timesteps N` | Env steps to train |
| `--from ID\|NAME` | Resume weights from an existing checkpoint |
| `--branch-as NAME` | With `--from`, fork a new entry named `NAME` then train it |
| `--rollout-steps` | PPO rollout length before each update |
| `--checkpoint-every` / `--eval-every` | Cadence in env steps |
| `--device` | `cpu` or `cuda` |
| `--reward-mode` | `rank` (+1…−1 by finish) or `points` |

**Examples**

```bash
convoy-train --league runs/league --name main --players 3 --timesteps 50000
```

Starts a new learner called `main`, trains for 50k env steps in 3-player games,
and stores init / periodic / final checkpoints under `runs/league`. Opponents are
a mix of the live policy (mirror self-play) and active league checkpoints.

```bash
convoy-train --league runs/league --from <id> --branch-as aggressive --timesteps 20000
```

Copies `<id>` into a new league entry `aggressive`, then trains that fork for
20k more steps. Use this to grow a named variant away from `main`.

Without `--branch-as`, `--from` resumes training on the same lineage name
(`--name`) while still recording new checkpoints that point at the parent.

### `convoy-league`

Manages the on-disk league: list, branch, promote, eval, export.

Shared flag: `--league DIR` (default `runs/league`).

#### `list`

```bash
convoy-league --league runs/league list
convoy-league --league runs/league list --active --tag playtest
```

Prints id, name, parent, step, tags. Use an id from here as `<id>` in other
commands.

#### `show`

```bash
convoy-league --league runs/league show <id-or-name>
```

One entry plus its parent chain (root → … → entry).

#### `branch`

```bash
convoy-league --league runs/league branch <id> --name aggressive
```

Forks checkpoint `<id>` into a new entry named `aggressive` with
`parent_id = <id>`. Weights match the parent at fork time; this does **not**
train. Training the fork is a separate `convoy-train --from … --branch-as …`
(or `--from aggressive` later).

#### `promote`

```bash
convoy-league --league runs/league promote <id-or-name> --tag playtest
```

Marks a bot for playtesting (keeps it active and adds a tag). Optional
`--name` renames the entry.

#### `set-active`

```bash
convoy-league --league runs/league set-active <id-or-name>
convoy-league --league runs/league set-active <id-or-name> --off
```

Controls whether the checkpoint is sampled as a training opponent.

#### `eval`

```bash
convoy-league --league runs/league eval aggressive --episodes 20
```

Loads `aggressive` (by name or id), plays N games with that bot in one seat and
random agents in the others, then prints win rate and mean return. Quick check
that a bot is worth playtesting.

#### `export`

```bash
convoy-league --league runs/league export aggressive -o bots/playtest.pt
```

Copies the checkpoint file for use outside the league directory.

## League layout

```
runs/league/
  league.json          # registry: id, name, parent_id, tags, metrics
  checkpoints/
    <id>.pt            # policy weights + meta
```

Branching only copies weights and records lineage; each continued
`convoy-train` run appends new child checkpoints.

## Python API

```python
from sixtyfivekmconvoy.rl import League, RLAgent, SelfPlayTrainer

league = League("runs/league")
bot = RLAgent(league.load_model("playtest"), deterministic=True)
# bot.act(obs_vec, legal_actions, action_mask=mask) → index into legal_actions
```

PettingZoo env details (obs / action mask) are in the main [README](../README.md).

## Related CLIs

| Command | Role |
|---------|------|
| `convoy-selfplay` | Random-agent episodes (no learning) |
| `convoy-train` | PPO self-play into a league |
| `convoy-league` | Branch / promote / eval / export bots |
| `convoy-web` / `convoy-terminal` | Human play (bots still random unless wired to a checkpoint) |
