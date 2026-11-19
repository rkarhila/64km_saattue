#!/usr/bin/env python3
"""Continue retire training from the latest checkpoint.

Adam starts at 1e-3 and falls linearly to 3e-4 across ``--hours`` (default
6). Eval still uses 32 games. The league, log, and resume rule are the same
as ``train_6h_retire.py``.

Run on the GTX 1050 machine, from ``dev/``::

    PYTHONPATH=src python scripts/train_6h_decay.py
"""

from __future__ import annotations

import os
import sys

os.environ["CONVOY_CONFIG"] = "retire"

from train_6h_retire import main


def _with_schedule(argv: list[str]) -> list[str]:
    extra: list[str] = []
    if "--lr" not in argv:
        extra.extend(["--lr", "1e-3"])
    if "--lr-end" not in argv:
        extra.extend(["--lr-end", "3e-4"])
    return extra + argv


if __name__ == "__main__":
    main(_with_schedule(sys.argv[1:]))
