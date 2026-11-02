"""推送到手机。

目前只实现 ntfy（最轻、最干净、不依赖任何账号）。
以后想换成飞书/企业微信/Server酱，在 CHANNELS 里加一个函数即可。

防重复：同一天只推一次，除非 --force-push。
因为「双击 bat」很容易点两下，不该收到两条一样的推送。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

LOG = logging.getLogger("push")

STATE_FILE = "push_state.json"


def default_page_url() -> str:
    """云端（GitHub Actions）自动推断 Pages 地址。

    Actions 里 GITHUB_REPOSITORY 形如 'owner/repo'，
    对应 https://owner.github.io/repo/web/index.html。
    本地跑时没有这个变量，返回空字符串。
    """
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner.lower()}.github.io/{name}/web/index.html"
    return ""


def _state_path(data_dir: Path) -> Path:
    return Path(data_dir) / STATE_FILE


def _load_state(data_dir: Path) -> dict[str, Any]:
    path = _state_path(data_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(data_dir: Path, state: dict[str, Any]) -> None:
    path = _state_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def already_pushed_today(data_dir: Path, day: str) -> bool:
    return _load_state(data_dir).get("last_day") == day


def mark_pushed(data_dir: Path, day: str) -> None:
    state = _load_state(data_dir)
    state["last_day"] = day
    state["last_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    _save_state(data_dir, state)


def send_ntfy(
    server: str,
    topic: str,
    *,
    title: str,
    message: str,
    click: str = "",
    priority: int = 3,
    tags: list[str] | None = None,
    timeout: int = 20,
) -> bool:
    payload: dict[str, Any] = {
        "topic": topic,
        "title": title,
        "message": message,
        "priority": int(priority),
    }
    if click:
        payload["click"] = click
    if tags:
        payload["tags"] = tags

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        resp = requests.post(
            server.rstrip("/") + "/",
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        LOG.warning("推送请求失败：%s", exc)
        return False

    if resp.status_code != 200:
        LOG.warning("推送返回 %s：%s", resp.status_code, resp.text[:200])
        return False
    try:
        info = resp.json()
    except ValueError:
        info = {}
    LOG.info("推送已发出（id=%s, event=%s）", info.get("id"), info.get("event"))
    return True


def _compose(day_data: dict[str, Any]) -> tuple[str, str]:
    """把一天的卡片包压成一条手机上看得到的通知。"""
    day = day_data.get("day") or datetime.now().strftime("%Y-%m-%d")
    cards = day_data.get("cards") or []
    concept = next((c for c in cards if c.get("kind") == "concept"), None)
    frontier = next((c for c in cards if c.get("kind") == "frontier"), None)
    quiz_count = sum(1 for c in cards if c.get("kind") == "quiz")

    title = f"具身日报 · {day[5:]}"

    lines: list[str] = []
    if concept:
        lines.append(f"概念：{concept.get('title', '')}")
        lines.append(f"自测 {quiz_count} 道")
    if frontier:
        f_title = str(frontier.get("title", ""))
        if len(f_title) > 42:
            f_title = f_title[:41].rstrip() + "…"
        lines.append(f"前沿：{f_title}")
        reason = frontier.get("reason")
        if reason:
            lines.append(f"（{reason}）")
    if not lines:
        lines.append("今天没有生成新内容")

    return title, "\n".join(lines)


def push_daily(
    cfg: dict[str, Any],
    day_data: dict[str, Any],
    data_dir: Path,
    *,
    force: bool = False,
) -> bool:
    """按配置把今天的卡片包推到手机。返回是否真的发了。"""
    push_cfg = cfg.get("push") or {}
    channel = str(push_cfg.get("channel") or "off").strip().lower()
    day = str(day_data.get("day") or datetime.now().strftime("%Y-%m-%d"))

    if channel in ("", "off", "none", "false"):
        LOG.info("推送未启用（push.channel = %s）", channel or "空")
        return False

    if not force and already_pushed_today(data_dir, day):
        LOG.info("今天已经推过了（%s），跳过。要重发用 --force-push", day)
        return False

    title, message = _compose(day_data)
    click = str(push_cfg.get("url") or "").strip() or default_page_url()
    if click:
        LOG.info("推送附带链接：%s", click)

    ok = False
    if channel == "ntfy":
        server = str(push_cfg.get("server") or "https://ntfy.sh")
        topic = str(push_cfg.get("topic") or "").strip()
        if not topic:
            LOG.warning("push.topic 没配置，无法推送")
            return False
        ok = send_ntfy(
            server,
            topic,
            title=title,
            message=message,
            click=click,
            priority=int(push_cfg.get("priority") or 3),
            tags=["robot"],
        )
    else:
        LOG.warning("不认识的推送渠道：%s", channel)
        return False

    if ok:
        mark_pushed(data_dir, day)
    return ok
