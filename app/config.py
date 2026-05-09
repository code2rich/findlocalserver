from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml


DEFAULT_CONFIG = {
    "services": [],
    "ignore": {
        "ports": [],
        "processes": [],
    },
    "http_probe": {
        "enabled": True,
        "timeout": 2,
    },
    "refresh_interval": 30,
    "server": {
        "host": "0.0.0.0",
        "port": 9999,
    },
}


def load_config(config_path: str | Path | None = None) -> dict:
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"
    else:
        config_path = Path(config_path)

    config = dict(DEFAULT_CONFIG)

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
        _deep_merge(config, user_config)

    return config


def _deep_merge(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def get_manual_services(config: dict) -> list[dict]:
    return config.get("services", [])


def get_ignore_ports(config: dict) -> list[int]:
    return config.get("ignore", {}).get("ports", [])


def get_ignore_processes(config: dict) -> list[str]:
    return config.get("ignore", {}).get("processes", [])


def get_http_probe_config(config: dict) -> dict:
    return config.get("http_probe", {"enabled": True, "timeout": 2})


def get_refresh_interval(config: dict) -> int:
    return config.get("refresh_interval", 30)


def get_server_config(config: dict) -> dict:
    return config.get("server", {"host": "0.0.0.0", "port": 9999})
