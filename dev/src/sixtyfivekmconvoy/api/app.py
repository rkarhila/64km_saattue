"""FastAPI + WebSocket server for human-vs-bots play."""

from __future__ import annotations

import argparse
import hmac
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from sixtyfivekmconvoy.api.bots import list_league_bots
from sixtyfivekmconvoy.api.session import SessionManager


def _max_games_from_env() -> int:
    raw = os.environ.get("CONVOY_MAX_GAMES", "3")
    try:
        return max(1, int(raw))
    except ValueError:
        return 3


manager = SessionManager(max_games=_max_games_from_env())
app = FastAPI(title="65km Convoy", version="0.3.0")

# Start-page password. ``main`` replaces this from ``--password`` (default 1234).
_lobby_password = os.environ.get("CONVOY_PASSWORD") or "1234"
_gate_token = secrets.token_urlsafe(24)


def set_lobby_password(password: str | None) -> None:
    """Set the start-page password and invalidate previously issued tokens."""
    global _lobby_password, _gate_token
    text = (password or "").strip()
    _lobby_password = text or "1234"
    _gate_token = secrets.token_urlsafe(24)


def lobby_password_matches(password: str | None) -> bool:
    given = password or ""
    return hmac.compare_digest(given, _lobby_password)


def issue_gate_token() -> str:
    return _gate_token


def _require_gate(token: str | None) -> None:
    if not token or not hmac.compare_digest(token, _gate_token):
        raise HTTPException(401, "Salasana puuttuu.")

_WEB_ROOT = Path(__file__).resolve().parents[3] / "web"


class CreateGameRequest(BaseModel):
    num_players: int = Field(default=3, ge=2, le=5)
    human_seat: int = Field(default=0, ge=0, le=4)
    seed: int | None = None
    max_rounds: int = 200
    pause_after_actions: bool = True
    bot_kind: str = Field(default="random", description="random | rl")
    bot_id: str | None = Field(
        default=None, description="League checkpoint id or name when bot_kind=rl"
    )
    league_path: str | None = Field(
        default=None, description="Override league directory (server default otherwise)"
    )


class CreateGameResponse(BaseModel):
    game_id: str
    human_seat: str
    snapshot: dict


class ChoiceMessage(BaseModel):
    choice: list[int]


class PauseSettingMessage(BaseModel):
    pause_after_actions: bool


class ImportGameRequest(BaseModel):
    state: str


class CreateTableRequest(BaseModel):
    num_players: int = Field(default=3, ge=2, le=5)
    name: str = ""
    seed: int | None = None
    max_rounds: int = 200
    pause_after_actions: bool = True
    bot_kind: str = "random"
    bot_id: str | None = None
    league_path: str | None = None


class JoinTableRequest(BaseModel):
    name: str = ""


class UnlockRequest(BaseModel):
    password: str = ""


def _check_bot(kind: str, bot_id: str | None) -> str:
    cleaned = (kind or "random").strip().lower()
    if cleaned not in ("random", "rl"):
        raise HTTPException(400, "bot_kind must be 'random' or 'rl'")
    if cleaned == "rl" and not bot_id:
        raise HTTPException(400, "bot_id required when bot_kind=rl")
    return cleaned


@app.post("/lobby/unlock")
def unlock_lobby(body: UnlockRequest):
    if not lobby_password_matches(body.password):
        raise HTTPException(401, "Väärä salasana.")
    return {"token": issue_gate_token()}


@app.get("/lobby")
def get_lobby(x_convoy_token: str | None = Header(default=None)):
    _require_gate(x_convoy_token)
    return manager.lobby_status()


@app.post("/tables")
def post_table(
    body: CreateTableRequest,
    x_convoy_token: str | None = Header(default=None),
):
    _require_gate(x_convoy_token)
    kind = _check_bot(body.bot_kind, body.bot_id)
    try:
        table = manager.create_table(
            num_players=body.num_players,
            name=body.name,
            seed=body.seed,
            max_rounds=body.max_rounds,
            pause_after_actions=body.pause_after_actions,
            bot_kind=kind,
            bot_id=body.bot_id,
            league_path=body.league_path,
        )
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"table_id": table.table_id, "seat": 0, "table": table.public()}


@app.get("/tables/{table_id}")
def get_table(table_id: str, x_convoy_token: str | None = Header(default=None)):
    _require_gate(x_convoy_token)
    try:
        table = manager.get_table(table_id)
    except KeyError:
        raise HTTPException(404, "table not found")
    return table.public()


@app.post("/tables/{table_id}/join")
def post_join(
    table_id: str,
    body: JoinTableRequest,
    x_convoy_token: str | None = Header(default=None),
):
    _require_gate(x_convoy_token)
    try:
        table, seat = manager.join_table(table_id, body.name)
    except KeyError:
        raise HTTPException(404, "table not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"table_id": table.table_id, "seat": seat, "table": table.public()}


@app.post("/tables/{table_id}/start", response_model=CreateGameResponse)
def post_start(
    table_id: str,
    seat: int = 0,
    x_convoy_token: str | None = Header(default=None),
):
    _require_gate(x_convoy_token)
    try:
        session, human = manager.start_table(table_id, seat)
    except KeyError:
        raise HTTPException(404, "table not found")
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return CreateGameResponse(
        game_id=session.game_id,
        human_seat=human,
        snapshot=session.snapshot(human),
    )


@app.get("/league/bots")
def get_league_bots(league: str | None = None):
    """Lobby dropdown: active league checkpoints (reads league.json, no torch)."""
    return list_league_bots(Path(league) if league else None)


@app.post("/games", response_model=CreateGameResponse)
def create_game(body: CreateGameRequest):
    if body.human_seat >= body.num_players:
        raise HTTPException(400, "human_seat out of range")
    kind = (body.bot_kind or "random").strip().lower()
    if kind not in ("random", "rl"):
        raise HTTPException(400, "bot_kind must be 'random' or 'rl'")
    if kind == "rl" and not body.bot_id:
        raise HTTPException(400, "bot_id required when bot_kind=rl")
    try:
        session = manager.create(
            num_players=body.num_players,
            human_seat=body.human_seat,
            seed=body.seed,
            max_rounds=body.max_rounds,
            pause_after_actions=body.pause_after_actions,
            bot_kind=kind,
            bot_id=body.bot_id,
            league_path=body.league_path,
        )
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc
    human = f"player_{body.human_seat}"
    return CreateGameResponse(
        game_id=session.game_id,
        human_seat=human,
        snapshot=session.snapshot(human),
    )


@app.post("/games/import", response_model=CreateGameResponse)
def import_game(body: ImportGameRequest):
    try:
        session = manager.create_from_state_string(body.state)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Failed to import game: {exc}") from exc
    human_id = next(iter(session.human_seats))
    return CreateGameResponse(
        game_id=session.game_id,
        human_seat=human_id,
        snapshot=session.snapshot(human_id),
    )


def _session_or_404(game_id: str):
    try:
        return manager.get(game_id)
    except KeyError:
        raise HTTPException(404, "game not found")


@app.get("/games/{game_id}")
def get_game(game_id: str, seat: int = 0):
    session = _session_or_404(game_id)
    with session.turn_lock:
        return session.snapshot(f"player_{seat}")


@app.post("/games/{game_id}/choice")
def post_choice(game_id: str, body: ChoiceMessage, seat: int = 0):
    session = _session_or_404(game_id)
    player_id = f"player_{seat}"
    try:
        with session.turn_lock:
            return session.apply_human_choice(player_id, body.choice)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/games/{game_id}/continue")
def post_continue(game_id: str, seat: int = 0):
    session = _session_or_404(game_id)
    with session.turn_lock:
        return session.continue_play(f"player_{seat}")


@app.post("/games/{game_id}/settings")
def post_settings(game_id: str, body: PauseSettingMessage, seat: int = 0):
    session = _session_or_404(game_id)
    player_id = f"player_{seat}"
    with session.turn_lock:
        was_paused = session.awaiting_continue
        session.set_pause_after_actions(body.pause_after_actions)
        # Turning pause off while waiting should resume play.
        if was_paused and not body.pause_after_actions:
            return session.continue_play(player_id)
        return session.snapshot(player_id)


@app.websocket("/games/{game_id}/ws")
async def game_ws(websocket: WebSocket, game_id: str, seat: int = 0):
    await websocket.accept()
    try:
        session = manager.get(game_id)
    except KeyError:
        await websocket.close(code=4404)
        return

    player_id = f"player_{seat}"
    with session.turn_lock:
        opening = session.snapshot(player_id)
    await websocket.send_json(opening)

    try:
        while True:
            data = await websocket.receive_json()
            choice = data.get("choice")
            if choice is None:
                await websocket.send_json({"error": "missing choice"})
                continue
            async with session.lock:
                try:
                    with session.turn_lock:
                        snap = session.apply_human_choice(player_id, list(choice))
                except ValueError as exc:
                    await websocket.send_json({"error": str(exc)})
                    continue
            await websocket.send_json(snap)
            if snap.get("terminal"):
                break
    except WebSocketDisconnect:
        return


@app.get("/")
def index():
    index_path = _WEB_ROOT / "index.html"
    if not index_path.exists():
        raise HTTPException(404, f"web UI not found at {index_path}")
    from sixtyfivekmconvoy.core.card_display import fill_rules_html

    html = fill_rules_html(index_path.read_text(encoding="utf-8"))
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


if _WEB_ROOT.exists():
    app.mount("/static", StaticFiles(directory=str(_WEB_ROOT)), name="static")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serve 65km Convoy web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--max-games",
        type=int,
        default=3,
        help="How many waiting or in-progress games this process may hold",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("CONVOY_PASSWORD") or "1234",
        help="Password required on the start page (default 1234)",
    )
    args = parser.parse_args(argv)
    global manager
    manager = SessionManager(max_games=max(1, args.max_games))
    set_lobby_password(args.password)
    import uvicorn

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
