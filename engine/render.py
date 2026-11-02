"""渲染电脑端待读队列（reading/queue.md）。

电脑端和手机端的区别不在于条数，在于「能不能动手」和「有没有脉络」：
这里每条都带 arXiv 链接、PDF、代码仓库、分数拆解，供你挑一条读一晚上。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .models import Item

TRACK_LABEL = {"perception": "感知", "control": "控制", "general": "通用"}


def _age_text(it: Item) -> str:
    hours = it.age_hours
    if hours < 1:
        return "刚刚"
    if hours < 24:
        return f"{hours:.0f} 小时前"
    return f"{hours / 24:.1f} 天前"


def _links(it: Item) -> list[str]:
    links: list[str] = []
    extra = it.extra
    if extra.get("arxiv_id"):
        links.append(f"[arXiv](https://arxiv.org/abs/{extra['arxiv_id']})")
    if extra.get("pdf"):
        links.append(f"[PDF]({extra['pdf']})")
    if extra.get("github"):
        links.append(f"[代码]({extra['github']})")
    if extra.get("project"):
        links.append(f"[主页]({extra['project']})")
    if extra.get("hn_url"):
        links.append(f"[HN 讨论]({extra['hn_url']})")
    if not links:
        links.append(f"[原文]({it.url})")
    return links


def _block(idx: int, it: Item) -> str:
    track = it.score_parts.get("track", "general")
    matched = it.score_parts.get("matched") or []
    lines = [
        f"### {idx}. `{it.score:.2f}` {it.title}",
        "",
        f"- {TRACK_LABEL.get(str(track), track)} · {it.source} · {_age_text(it)}",
        "- " + " · ".join(_links(it)),
    ]
    if it.summary:
        lines.append(f"- {it.summary[:260]}{'…' if len(it.summary) > 260 else ''}")
    if matched:
        lines.append(f"- 命中关键词：{', '.join(map(str, matched))}")
    if it.extra.get("stars"):
        lines.append(f"- ⭐ {it.extra['stars']}")
    lines.append("")
    lines.append("- [ ] 已读")
    lines.append("")
    return "\n".join(lines)


def render_queue(
    items: list[Item],
    *,
    day: str | None = None,
    threshold_mobile: float = 7.0,
    threshold_pc: float = 5.0,
    new_count: int | None = None,
    offline: bool = False,
) -> str:
    day = day or datetime.now().strftime("%Y-%m-%d")
    top = [i for i in items if i.score >= threshold_mobile]
    mid = [i for i in items if threshold_pc <= i.score < threshold_mobile]
    below = [i for i in items if i.score < threshold_pc]

    out: list[str] = [
        f"# 待读队列 · {day}",
        "",
        f"> {'离线重算' if offline else '本次抓取'}：共 {new_count if new_count is not None else len(items)} 条新内容",
        f"> 手机级（≥{threshold_mobile}）：{len(top)} 条 · 电脑级（≥{threshold_pc}）：{len(top) + len(mid)} 条",
        "",
        "挑一条，读两小时。手机端只推第一条。",
        "",
        "---",
        "",
        f"## 🔥 值得花时间（{threshold_mobile}+）",
        "",
    ]
    if top:
        out.extend(_block(i, it) for i, it in enumerate(top, 1))
    else:
        out.extend(["今天没有达到手机级阈值的内容。宁缺毋滥。", ""])

    out.extend(["---", "", f"## 📋 备选（{threshold_pc}–{threshold_mobile}）", ""])
    if mid:
        out.extend(_block(i, it) for i, it in enumerate(mid, 1))
    else:
        out.append("（空）")
        out.append("")

    if below:
        out.extend(["---", "", f"## 🗑 已过滤（<{threshold_pc}，共 {len(below)} 条）", ""])
        for it in below[:25]:
            out.append(f"- `{it.score:.2f}` {it.title[:80]}")
        if len(below) > 25:
            out.append(f"- …另有 {len(below) - 25} 条")
        out.append("")

    return "\n".join(out)


def write_queue(markdown: str, reading_dir: Path, day: str) -> Path:
    reading_dir.mkdir(parents=True, exist_ok=True)
    (reading_dir / "archive").mkdir(parents=True, exist_ok=True)
    current = reading_dir / "queue.md"
    current.write_text(markdown, encoding="utf-8")
    (reading_dir / "archive" / f"{day}.md").write_text(markdown, encoding="utf-8")
    return current
