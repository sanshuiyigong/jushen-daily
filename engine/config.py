"""配置加载。

用 YAML 而不是 TOML：yolov5 环境是 Python 3.8，标准库没有 tomllib。
聊天窗口以后会改 config.yaml，这里只负责读，不做任何写操作。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_NAME = "config.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else ROOT / CONFIG_NAME
    if not cfg_path.exists():
        raise FileNotFoundError(f"找不到配置文件：{cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"配置文件格式不对（顶层必须是映射）：{cfg_path}")
    return data


def get(cfg: dict[str, Any], dotted: str, default: Any = None) -> Any:
    """按 'sources.arxiv_ro.weight' 这样的路径取值。"""
    node: Any = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def paths(cfg: dict[str, Any]) -> dict[str, Path]:
    """把配置里的相对路径解析成绝对路径。"""
    raw = cfg.get("paths", {}) or {}
    out: dict[str, Path] = {}
    for key in ("data", "output", "reading", "web", "curriculum"):
        out[key] = (ROOT / raw.get(key, key)).resolve()
        out[key].mkdir(parents=True, exist_ok=True)
    return out
