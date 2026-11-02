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

from .net import detect_local_proxy, make_session

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
    timeout: int = 25,
    session: requests.Session | None = None,
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
        resp = (session or make_session()).post(
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


LETTERS = "ABCDEF"


def _clip_bytes(text: str, limit: int = 3600) -> str:
    """按 UTF-8 字节数截断。ntfy 默认消息上限 4096 字节，中文一个字 3 字节。"""
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    cut = raw[:limit].decode("utf-8", errors="ignore")
    return cut.rstrip() + "\n…（截断了，完整版点开链接看）"


def _full_body(cards: list[dict[str, Any]]) -> str:
    """把概念卡、题目、前沿拼成一条能在通知里直接读完的正文。

    答案单独放在最后一段，这样你可以先在通知里自测，再往下滑对答案。
    """
    parts: list[str] = []

    concept = next((c for c in cards if c.get("kind") == "concept"), None)
    if concept:
        parts.append(f"▍{concept.get('title', '')}")
        parts.append("")
        body = str(concept.get("body") or "").strip()
        if body:
            parts.append(body)
        if concept.get("analogy"):
            parts.append("")
            parts.append(f"打个比方：{concept['analogy']}")
        if concept.get("misconception"):
            parts.append(f"常见误解：{concept['misconception']}")

    quizzes = [c for c in cards if c.get("kind") == "quiz"]
    if quizzes:
        parts.append("")
        parts.append("▍自测")
        parts.append("")
        for i, q in enumerate(quizzes, 1):
            parts.append(f"{i}. {q.get('question', '')}")
            for j, opt in enumerate(q.get("options") or []):
                parts.append(f"   {LETTERS[j] if j < len(LETTERS) else j}. {opt}")
            parts.append("")
        parts.append("▍答案")
        parts.append("")
        for i, q in enumerate(quizzes, 1):
            try:
                ans = int(q.get("answer", 0))
            except (TypeError, ValueError):
                ans = 0
            letter = LETTERS[ans] if 0 <= ans < len(LETTERS) else str(ans)
            explain = str(q.get("explain") or "").strip()
            parts.append(f"{i}. {letter}" + (f" —— {explain}" if explain else ""))

    frontier = next((c for c in cards if c.get("kind") == "frontier"), None)
    if frontier:
        parts.append("")
        parts.append("▍前沿")
        parts.append("")
        parts.append(str(frontier.get("title", "")))
        if frontier.get("oneline"):
            parts.append(str(frontier["oneline"]))
        if frontier.get("why"):
            parts.append(f"→ {frontier['why']}")

    return _clip_bytes("\n".join(parts))


def _compose(day_data: dict[str, Any], *, full: bool = True) -> tuple[str, str]:
    """把一天的卡片包压成一条手机上看得到的通知。"""
    day = day_data.get("day") or datetime.now().strftime("%Y-%m-%d")
    cards = day_data.get("cards") or []
    title = f"具身日报 · {day[5:]}"

    if full:
        body = _full_body(cards)
        if body.strip():
            return title, body

    # 简短版（或者开启 full 但没有内容时退回）
    concept = next((c for c in cards if c.get("kind") == "concept"), None)
    frontier = next((c for c in cards if c.get("kind") == "frontier"), None)
    quiz_count = sum(1 for c in cards if c.get("kind") == "quiz")

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

    title, message = _compose(day_data, full=bool(push_cfg.get("include_content", True)))
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

        # 代理：显式配置优先，其次自动探测本地代理（云端不会命中，自动直连）
        proxy_url = str(push_cfg.get("proxy") or "").strip()
        if not proxy_url and bool(push_cfg.get("auto_proxy", True)):
            proxy_url = detect_local_proxy()
        session = make_session(proxy=proxy_url)   # "" = 强制直连
        if proxy_url:
            LOG.info("推送将走代理 %s", proxy_url)
        else:
            LOG.info("推送直连（未探测到本地代理）")

        ok = send_ntfy(
            server,
            topic,
            title=title,
            message=message,
            click=click,
            priority=int(push_cfg.get("priority") or 3),
            tags=["robot"],
            session=session,
        )
    else:
        LOG.warning("不认识的推送渠道：%s", channel)
        return False

    if ok:
        mark_pushed(data_dir, day)
    return ok


if __name__ == "__main__":
    """预览 / 手动发送当天的推送。

        python -m engine.push            只预览，不发
        python -m engine.push --send     预览并真的发到手机
    """
    import sys

    from .config import load_config, paths

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s", stream=sys.stdout)
    cfg = load_config()
    p = paths(cfg)
    today = datetime.now().strftime("%Y-%m-%d")

    # 优先用今天的；今天还没生成就退回到最近一份，方便随时预览
    day_dir = p["output"] / "days"
    target = day_dir / f"day-{today}.json"
    if not target.exists():
        candidates = sorted(day_dir.glob("day-*.json"))
        if not candidates:
            print(f"还没有任何卡片包：{day_dir}")
            print("先跑一次 run.py 生成内容。")
            raise SystemExit(1)
        target = candidates[-1]
        print(f"今天（{today}）还没生成，用最近一份预览：{target.name}")

    data = json.loads(target.read_text(encoding="utf-8"))
    title, body = _compose(data, full=bool((cfg.get("push") or {}).get("include_content", True)))

    print()
    print("=" * 64)
    print(f"标题: {title}")
    print(f"正文: {len(body.encode('utf-8'))} 字节 / {len(body)} 字符")
    print("=" * 64)
    print(body)
    print("=" * 64)

    if "--send" in sys.argv:
        print("\n正在发送…")
        sent = push_daily(cfg, data, p["data"], force=True)
        print("结果:", "已发送到手机 ✓" if sent else "发送失败 ✗")
    else:
        print("\n（只是预览。要真的发出去，加 --send）")
