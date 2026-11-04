"""组装一天的一包卡片，并合并出手机上要的 recent7.json。

分工：
  card.py    负责「造一张卡」
  cardset.py 负责「今天该出哪几张」和「打包」（本文件）

一包 = 1 张概念卡 + N 张题卡 + M 张前沿卡。
概念卡和题卡来自课程骨架；前沿卡来自当天打分结果。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .card import concept_card, frontier_card, quiz_cards
from .curriculum import Curriculum
from .clock import stamp as stamp_bj
from .llm import LLMClient
from .models import Item
from .rerank import pick_best

LOG = logging.getLogger("cardset")

TRACK_LABEL = {"perception": "感知", "control": "控制", "general": "通用"}


def build_day(
    ranked: list[Item],
    cfg: dict[str, Any],
    day: str,
    *,
    llm: LLMClient | None = None,
    curriculum: Curriculum | None = None,
) -> dict[str, Any]:
    general = cfg.get("general") or {}
    ranking = cfg.get("ranking") or {}
    frontier_limit = int(general.get("mobile_frontier_max", 1))
    quiz_limit = int(general.get("quiz_per_day", 2))
    threshold = float(ranking.get("mobile_threshold", 7.0))

    cards: list[dict[str, Any]] = []
    node_info: dict[str, Any] | None = None

    # ---- 概念卡 + 题卡（来自课程骨架）----
    if curriculum is not None:
        picked = curriculum.next_overall()
        if picked:
            track_name, node = picked
            track_label = (curriculum.tracks.get(track_name) or {}).get("name", track_name)
            cards.append(concept_card(node, track_label, day, llm))
            cards.extend(quiz_cards(node, day, quiz_limit, llm))
            node_info = {
                "track": track_name,
                "track_label": track_label,
                "node_id": node.get("id"),
                "title": node.get("title"),
                "estimated_days": node.get("estimated_days"),
            }
            LOG.info("今日概念：%s · %s", track_label, node.get("title"))

    # ---- 前沿卡 ----
    track_hint = ""
    if node_info:
        track_hint = TRACK_LABEL.get(node_info["track"], node_info["track_label"])

    # 宁缺毋滥：没有条目越过阈值，今天就只推概念和题。
    # 绝不「退而取规则分前几名」——那会把 2 分的垃圾当成今天的前沿推出去。
    pool = [it for it in ranked if it.score >= threshold]
    if not pool:
        LOG.info("没有条目越过手机阈值（%s）—— 今天只推概念和题", threshold)

    picked: Item | None = None
    meta: dict[str, Any] = {}
    if pool and llm is not None and llm.available:
        result = pick_best(pool, llm, limit=max(8, frontier_limit * 4), track_hint=track_hint)
        if result:
            picked, meta = result
            LOG.info("前沿精排：%s", meta.get("reason", ""))
    elif pool:
        # 没 LLM 时退回规则分第一名
        picked = pool[0]

    if picked is not None:
        card = frontier_card(
            picked,
            day,
            llm=None,
            track_hint=track_hint,
            oneline_override=str(meta.get("oneline") or ""),
            why_override=str(meta.get("why") or ""),
        )
        if meta.get("reason"):
            card["reason"] = meta["reason"]
        cards.append(card)

    counts = {"concept": 0, "quiz": 0, "frontier": 0}
    for c in cards:
        counts[c["kind"]] = counts.get(c["kind"], 0) + 1

    return {
        "day": day,
        "generated_at": stamp_bj(),
        "llm": bool(llm and llm.available),
        "node": node_info,
        # 今天选中的前沿是哪一条（用于推送成功后标记 pushed，避免明天重复推）
        "picked_key": picked.key if picked is not None else "",
        "counts": counts,
        "cards": cards,
    }


def write_day(output_dir: Path, day_data: dict[str, Any]) -> Path:
    days_dir = Path(output_dir) / "days"
    days_dir.mkdir(parents=True, exist_ok=True)
    path = days_dir / f"day-{day_data['day']}.json"
    path.write_text(json.dumps(day_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_recent(output_dir: Path, keep_days: int = 7) -> Path:
    """把最近 N 天的卡片包合并成 recent7.json —— 手机端只请求这一个文件。"""
    days_dir = Path(output_dir) / "days"
    files = sorted(days_dir.glob("day-*.json"), key=lambda p: p.name, reverse=True)[:keep_days]
    days: list[dict[str, Any]] = []
    cards: list[dict[str, Any]] = []
    for f in sorted(files, key=lambda p: p.name):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            LOG.warning("跳过损坏的卡片包：%s", f.name)
            continue
        day_cards = data.get("cards", [])
        days.append({"day": data.get("day"), "count": len(day_cards)})
        cards.extend(day_cards)

    payload = {
        "generated_at": stamp_bj(),
        "keep_days": keep_days,
        "days": days,
        "cards": cards,
    }
    path = Path(output_dir) / "recent7.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
