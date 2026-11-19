"""One human against bots, with no web server.

The desktop server in ``api.app`` and the Pyodide worker both speak the same
lobby URLs. This module is the in-process side: it never imports FastAPI.
"""

from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from sixtyfivekmconvoy.api.session import GameSession, SessionManager

# Files the browser copies into Pyodide before importing this module.
# Training, the FastAPI app, and the PettingZoo env stay out.
_PYODIDE_FILES = (
    "__init__.py",
    "play.py",
    "api/__init__.py",
    "api/bots.py",
    "api/session.py",
    "rl/__init__.py",
    "rl/events.py",
    "env/__init__.py",
    "env/card_features.py",
    "env/spaces.py",
    "env/table_features.py",
    "play_net.py",
)


def pyodide_files() -> list[str]:
    """Package-relative paths the static page must fetch into Pyodide."""
    root = Path(__file__).resolve().parent
    rels: list[str] = []
    for folder in ("core", "agents", "data"):
        for path in sorted((root / folder).rglob("*")):
            if "__pycache__" in path.parts:
                continue
            if path.suffix not in {".py", ".csv"}:
                continue
            rels.append(path.relative_to(root).as_posix())
    rels.extend(_PYODIDE_FILES)
    missing = [rel for rel in rels if not (root / rel).is_file()]
    if missing:
        raise FileNotFoundError("pyodide bundle is missing " + ", ".join(missing))
    return list(dict.fromkeys(rels))


def _seat(query: dict[str, list[str]]) -> int:
    raw = (query.get("seat") or ["0"])[0]
    return int(raw)


def bot_observation(session: GameSession, player_id: str):
    """Float vector the browser policy will read.

    Random bots do not use it. The page keeps PyTorch out of Pyodide and, later,
    runs this vector through ONNX in JavaScript.
    """
    from sixtyfivekmconvoy.env.spaces import fill_observation

    seat = int(player_id.split("_")[1])
    return fill_observation(session.engine, seat, len(session.engine.players))


def new_solo(
    *,
    num_players: int = 3,
    name: str = "Pelaaja",
    seed: int | None = 1,
    max_rounds: int = 200,
    pause_after_actions: bool = True,
) -> GameSession:
    """Start one human in seat 0. The other seats are random bots."""
    manager = SessionManager()
    table = manager.create_table(
        num_players=num_players,
        name=name,
        seed=seed,
        max_rounds=max_rounds,
        pause_after_actions=pause_after_actions,
        bot_kind="random",
    )
    session, _human = manager.start_table(table.table_id)
    return session


class LocalLobby:
    """The lobby routes from ``api.app``, answered in-process.

    Game moves do not repeat the lobby password, matching the server.
    ``weights_path`` is a NumPy copy of the trained checkpoint. Without it,
    only the random bots are offered.
    """

    def __init__(self, password: str = "1234", weights_path: str | None = None) -> None:
        self.password = (password or "1234").strip() or "1234"
        self.token = "local-gate"
        self.manager = SessionManager()
        self.weights_path = weights_path or os.environ.get("CONVOY_BOT_WEIGHTS") or ""
        self._policy: Any = None

    def handle(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        try:
            return self._dispatch(method, url, body or {}, headers or {})
        except PermissionError as exc:
            return 401, {"detail": str(exc)}
        except KeyError:
            return 404, {"detail": "not found"}
        except ValueError as exc:
            return 400, {"detail": str(exc)}
        except RuntimeError as exc:
            return 409, {"detail": str(exc)}

    def _dispatch(
        self,
        method: str,
        url: str,
        body: dict[str, Any],
        headers: dict[str, str],
    ) -> tuple[int, Any]:
        parsed = urlparse(url)
        parts = [part for part in parsed.path.split("/") if part]
        query = parse_qs(parsed.query)
        method = method.upper()
        if method == "POST" and parts == ["lobby", "unlock"]:
            given = str(body.get("password") or "")
            if not hmac.compare_digest(given, self.password):
                raise PermissionError("Väärä salasana.")
            return 200, {"token": self.token}
        if method == "GET" and parts == ["rules", "placeholders"]:
            from sixtyfivekmconvoy.core.card_display import rules_placeholders

            return 200, rules_placeholders()
        if method == "GET" and parts == ["league", "bots"]:
            return 200, self._bots_payload()
        if len(parts) >= 1 and parts[0] == "games":
            return self._game(method, parts, query, body)
        self._require_gate(headers)
        if method == "GET" and parts == ["lobby"]:
            return 200, self.manager.lobby_status()
        if method == "POST" and parts == ["tables"]:
            kind = self._bot_kind(body.get("bot_kind"), body.get("bot_id"))
            table = self.manager.create_table(
                num_players=int(body.get("num_players") or 3),
                name=str(body.get("name") or ""),
                seed=body.get("seed"),
                max_rounds=int(body.get("max_rounds") or 200),
                pause_after_actions=bool(body.get("pause_after_actions", True)),
                bot_kind=kind,
                bot_id=body.get("bot_id"),
                league_path=body.get("league_path"),
            )
            return 200, {"table_id": table.table_id, "seat": 0, "table": table.public()}
        if len(parts) >= 2 and parts[0] == "tables":
            table_id = parts[1]
            if method == "GET" and len(parts) == 2:
                return 200, self.manager.get_table(table_id).public()
            if method == "POST" and parts[2:] == ["join"]:
                table, seat = self.manager.join_table(table_id, str(body.get("name") or ""))
                return 200, {"table_id": table.table_id, "seat": seat, "table": table.public()}
            if method == "POST" and parts[2:] == ["start"]:
                table = self.manager.get_table(table_id)
                session, human = self.manager.start_table(
                    table_id,
                    _seat(query),
                    external_bots=self._external_bots(table),
                )
                return 200, {
                    "game_id": session.game_id,
                    "human_seat": human,
                    "snapshot": session.snapshot(human),
                }
        raise KeyError(parsed.path)

    def _game(
        self,
        method: str,
        parts: list[str],
        query: dict[str, list[str]],
        body: dict[str, Any],
    ) -> tuple[int, Any]:
        if method == "POST" and parts == ["games", "import"]:
            session = self.manager.create_from_state_string(str(body.get("state") or ""))
            human_id = next(iter(session.human_seats))
            return 200, {
                "game_id": session.game_id,
                "human_seat": human_id,
                "snapshot": session.snapshot(human_id),
            }
        if len(parts) >= 2 and parts[0] == "games" and parts[1] != "import":
            session = self.manager.get(parts[1])
            player_id = f"player_{_seat(query)}"
            if method == "GET" and len(parts) == 2:
                return 200, session.snapshot(player_id)
            if method == "POST" and parts[2:] == ["choice"]:
                choice = body.get("choice")
                if not isinstance(choice, list):
                    raise ValueError("missing choice")
                return 200, session.apply_human_choice(player_id, [int(n) for n in choice])
            if method == "POST" and parts[2:] == ["continue"]:
                return 200, session.continue_play(player_id)
            if method == "POST" and parts[2:] == ["settings"]:
                enabled = bool(body.get("pause_after_actions"))
                was_paused = session.awaiting_continue
                session.set_pause_after_actions(enabled)
                if was_paused and not enabled:
                    return 200, session.continue_play(player_id)
                return 200, session.snapshot(player_id)
        raise KeyError(parsed.path)

    def _require_gate(self, headers: dict[str, str]) -> None:
        folded = {str(key).lower(): value for key, value in headers.items()}
        token = str(folded.get("x-convoy-token") or "")
        if not token or not hmac.compare_digest(token, self.token):
            raise PermissionError("Salasana puuttuu.")

    def policy(self) -> Any:
        if self._policy is None and self.weights_path and os.path.isfile(self.weights_path):
            from sixtyfivekmconvoy.play_net import NumpyPolicy

            self._policy = NumpyPolicy.load(self.weights_path)
        return self._policy

    def _bots_payload(self) -> dict[str, Any]:
        policy = self.policy()
        if policy is None:
            return {
                "league": self.weights_path,
                "exists": False,
                "bots": [],
                "searched": [self.weights_path] if self.weights_path else [],
                "error": None,
            }
        from sixtyfivekmconvoy.play_net import BOT_ID, BOT_NAME, BOT_STEP

        return {
            "league": self.weights_path,
            "exists": True,
            "bots": [
                {
                    "id": BOT_ID,
                    "name": BOT_NAME,
                    "step": BOT_STEP,
                    "label": f"{BOT_NAME} ({BOT_ID[:8]}, step {BOT_STEP})",
                }
            ],
            "searched": [],
            "error": None,
        }

    def _external_bots(self, table: Any) -> dict[str, Any] | None:
        if table.bot_kind != "rl":
            return None
        policy = self.policy()
        if policy is None:
            raise ValueError("Botti ei ole ladattu.")
        return {
            f"player_{seat}": policy
            for seat in range(table.num_players)
            if seat not in table.seats
        }

    def _bot_kind(self, kind: Any, bot_id: Any) -> str:
        cleaned = str(kind or "random").strip().lower()
        if cleaned not in ("random", "rl"):
            raise ValueError("bot_kind must be 'random' or 'rl'")
        if cleaned == "rl":
            if self.policy() is None:
                raise ValueError("Botti ei ole ladattu.")
            if not bot_id:
                raise ValueError("bot_id required when bot_kind=rl")
        return cleaned


def main(argv: list[str] | None = None) -> None:
    """Serve ``dev/`` so the browser can fetch this package and the page."""
    import argparse
    from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

    parser = argparse.ArgumentParser(
        description="Serve the one-player page (Pyodide) and this Python package"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    class Handler(SimpleHTTPRequestHandler):
        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    root = Path(__file__).resolve().parents[2]
    os.chdir(root)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Open http://{args.host}:{args.port}/web/local.html", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
