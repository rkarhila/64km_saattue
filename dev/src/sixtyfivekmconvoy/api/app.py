"""FastAPI + WebSocket server for human-vs-bots play."""

from __future__ import annotations

import argparse
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from sixtyfivekmconvoy.api.session import SessionManager

manager = SessionManager()
app = FastAPI(title="65km Convoy", version="0.2.0")

_WEB_ROOT = Path(__file__).resolve().parents[3] / "web"


class CreateGameRequest(BaseModel):
    num_players: int = Field(default=3, ge=2, le=5)
    human_seat: int = Field(default=0, ge=0, le=4)
    seed: int | None = 1
    max_rounds: int = 200
    pause_after_actions: bool = True


class CreateGameResponse(BaseModel):
    game_id: str
    human_seat: str
    snapshot: dict


class ChoiceMessage(BaseModel):
    choice: list[int]


class PauseSettingMessage(BaseModel):
    pause_after_actions: bool


@app.post("/games", response_model=CreateGameResponse)
def create_game(body: CreateGameRequest):
    if body.human_seat >= body.num_players:
        raise HTTPException(400, "human_seat out of range")
    session = manager.create(
        num_players=body.num_players,
        human_seat=body.human_seat,
        seed=body.seed,
        max_rounds=body.max_rounds,
        pause_after_actions=body.pause_after_actions,
    )
    human = f"player_{body.human_seat}"
    return CreateGameResponse(
        game_id=session.game_id,
        human_seat=human,
        snapshot=session.snapshot(human),
    )


@app.get("/games/{game_id}")
def get_game(game_id: str, seat: int = 0):
    try:
        session = manager.get(game_id)
    except KeyError:
        raise HTTPException(404, "game not found")
    return session.snapshot(f"player_{seat}")


@app.post("/games/{game_id}/choice")
def post_choice(game_id: str, body: ChoiceMessage, seat: int = 0):
    try:
        session = manager.get(game_id)
    except KeyError:
        raise HTTPException(404, "game not found")
    player_id = f"player_{seat}"
    try:
        return session.apply_human_choice(player_id, body.choice)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/games/{game_id}/continue")
def post_continue(game_id: str, seat: int = 0):
    try:
        session = manager.get(game_id)
    except KeyError:
        raise HTTPException(404, "game not found")
    return session.continue_play(f"player_{seat}")


@app.post("/games/{game_id}/settings")
def post_settings(game_id: str, body: PauseSettingMessage, seat: int = 0):
    try:
        session = manager.get(game_id)
    except KeyError:
        raise HTTPException(404, "game not found")
    was_paused = session.awaiting_continue
    session.set_pause_after_actions(body.pause_after_actions)
    player_id = f"player_{seat}"
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
    await websocket.send_json(session.snapshot(player_id))

    try:
        while True:
            data = await websocket.receive_json()
            choice = data.get("choice")
            if choice is None:
                await websocket.send_json({"error": "missing choice"})
                continue
            async with session.lock:
                try:
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
    return FileResponse(index_path)


if _WEB_ROOT.exists():
    app.mount("/static", StaticFiles(directory=str(_WEB_ROOT)), name="static")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serve 65km Convoy web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    import uvicorn

    uvicorn.run(
        "sixtyfivekmconvoy.api.app:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
