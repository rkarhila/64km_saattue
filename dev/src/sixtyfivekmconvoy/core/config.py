"""
Active game-balance settings.

Profiles live in ``sixtyfivekmconvoy.core.configs`` (default: ``default``).
Choose a profile with env ``CONVOY_CONFIG=<name>`` before importing the engine
so RL checkpoints stay conf-file specific.
"""

from __future__ import annotations

from .configs import config_name, get_config, load_config

_cfg = get_config()

# Re-export uppercase settings for `from ...config import FOO`.
for _key, _val in vars(_cfg).items():
    if _key.isupper():
        globals()[_key] = _val

CONFIG_NAME = config_name()

__all__ = sorted(k for k in globals() if k.isupper()) + [
    "CONFIG_NAME",
    "get_config",
    "load_config",
    "config_name",
]
