"""Start the Python play server on one version directory.

The engine reads its config and cards at import, so the version is applied
before ``api.app`` is imported.
"""

from __future__ import annotations

import argparse
import os


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serve 65km Convoy web UI")
    parser.add_argument(
        "--version",
        default=os.environ.get("CONVOY_VERSION") or "alpha_01",
        help="Version directory under dev/versions (default: alpha_01)",
    )
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
    from sixtyfivekmconvoy.boot import prepare_version, version_bots_dir

    try:
        root = prepare_version(args.version)
    except (ValueError, FileNotFoundError) as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Versio: {args.version} ({root})", flush=True)
    print(f"Botit: {version_bots_dir(args.version)}", flush=True)
    from sixtyfivekmconvoy.api.app import main as serve

    serve(
        [
            "--host",
            args.host,
            "--port",
            str(args.port),
            "--max-games",
            str(args.max_games),
            "--password",
            args.password,
        ]
    )


if __name__ == "__main__":
    main()
