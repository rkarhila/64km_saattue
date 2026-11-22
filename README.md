# 64km Saattue

Board game you play in the browser against bots. The engine and the web UI live in [`dev/`](dev/README.md).

Play in the browser, without installing Python: [rkarhila.github.io/64km_saattue/versions.html](https://rkarhila.github.io/64km_saattue/versions.html). Pick a version there. Each version is a directory under `dev/versions/` with its own `config.py` and card CSVs, and they all run the same engine. The first load downloads the engine. The password is 1234. Opening [playtest.html](https://rkarhila.github.io/64km_saattue/playtest.html) with no query starts the Alpha 01 version.

You need Python 3.11 or newer.

## Play against random bots

```bash
cd dev
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
convoy-web --version alpha_01 --host 127.0.0.1 --port 8000
```

`--version` picks a directory under `dev/versions/` before the engine loads. RL checkpoints for that version live in its `bots/` folder. Each checkpoint keeps a copy of `config.py` and the card CSVs, and the lobby warns if those files have changed since training.

Open http://127.0.0.1:8000/. Leave **Vastustajat** on **Satunnaiset botit** and press **Uusi peli**. You play the first seat. The other seats are random bots. No PyTorch and no checkpoint are required.

The same one-player game can run in the browser without the Python server staying up. From `dev/`:

```bash
PYTHONPATH=src python -m sixtyfivekmconvoy.play
```

Open http://127.0.0.1:8000/web/local.html. That page downloads Pyodide, loads the engine, and can play against random bots or a trained checkpoint stored in the chosen version's `bots/` folder. The password is 1234.

## Play against the trained bot

The trained policy is the release asset [`league_tf4h_v2.zip`](https://github.com/rkarhila/64km_saattue/releases/download/tf1050-step3346736/league_tf4h_v2.zip) (`tf1050-step3346736`, checkpoint `edefe53e3251`). It is the final network from a 4-hour run: 3,346,736 environment steps. Download it from the [release](https://github.com/rkarhila/64km_saattue/releases/tag/tf1050-step3346736) and unpack it into `dev/runs/`:

```bash
unzip league_tf4h_v2.zip -d dev/runs
```

That creates `dev/runs/league_tf4h_v2/` with `league.json` and `checkpoints/edefe53e3251.pt`.

Install the game with the PyTorch extra. A CPU build is enough to play; a GPU is only needed for training.

```bash
cd dev
python3 -m venv .venv
source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[rl]"
CONVOY_LEAGUE=runs/league_tf4h_v2 convoy-web --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/. Set **Vastustajat** to **League-RL -botti**. The **Botti (league)** list should show `tf1050-step3346736 (edefe53e, step 3346736)`. Press **Uusi peli**. You play the first seat, and the other seats share that policy.

`CONVOY_LEAGUE` must point at the directory that contains `league.json`. It overrides the version's `bots/` folder. Start the server from `dev/` so `runs/league_tf4h_v2` resolves. Checkpoints saved before this layout have no copy of the rules, so the lobby warns that the training rules were not stored.

Training notes are in [`dev/docs/rl-training.md`](dev/docs/rl-training.md).
