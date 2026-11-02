"""LLM 精排：从规则分 Top N 里挑出真正值得看的那一条。

规则分只懂关键词共现，不懂「这篇到底有没有实质内容」。
一次调用同时做三件事，成本不变：
  1. 选     —— 从候选里挑最值得读的
  2. 概括   —— 英文摘要转成一句中文（手机上读英文摘要体验很差）
  3. 关联   —— 说明它和课程骨架当前这一格有什么关系

没有 LLM、或解析失败时返回 None，调用方退回「规则分第一名 + 模板文案」。
"""

from __future__ import annotations

import logging
from typing import Any

from .llm import LLMClient
from .models import Item

LOG = logging.getLogger("rerank")

SYS = (
    "你是具身智能方向的研究助理，正在帮一个大二学生筛选每天该看的东西。"
    "这个学生在做视觉模块和上位机控制，目标是具身智能与机器人感知；"
    "视觉有一定基础，电控刚入门。"
    "判断标准：优先有实质方法贡献、有真机或公开实验、有代码的；"
    "排斥纯综述堆砌、纯 benchmark 刷分、和具身关系牵强的。"
)


def pick_best(
    items: list[Item],
    llm: LLMClient | None,
    *,
    limit: int = 8,
    track_hint: str = "",
) -> tuple[Item, dict[str, str]] | None:
    if not llm or not llm.available or not items:
        return None

    candidates = items[:limit]
    listing_parts = []
    for idx, it in enumerate(candidates):
        summary = (it.summary or "").strip().replace("\n", " ")[:320]
        link = ""
        if it.extra.get("github"):
            link = "  [有代码]"
        listing_parts.append(f"[{idx}] {it.title}{link}\n    {summary}")
    listing = "\n".join(listing_parts)

    user = f"""今天课程正在学：{track_hint or '具身感知'}

候选（规则分已排过序，但规则分只懂关键词，不懂实质内容）：
{listing}

请挑出最值得这个学生今天花时间读的一条，并输出 JSON：
{{"pick": 候选编号(整数),
 "oneline": "把摘要概括成一句中文，40 字以内，说清它做了什么",
 "why": "它和这个学生当前在学的东西有什么关系，40 字以内，要具体",
 "reason": "为什么选它而不是别的，30 字以内"}}

如果所有候选都不值得读，pick 填 -1。"""

    obj = llm.chat_json(SYS, user, temperature=0.2, max_tokens=400)
    if not obj:
        return None

    try:
        idx = int(obj.get("pick", -1))
    except (TypeError, ValueError):
        LOG.warning("精排返回的 pick 不是整数：%r", obj.get("pick"))
        return None

    if idx < 0:
        LOG.info("精排认为今天没有值得读的候选")
        return None
    if idx >= len(candidates):
        LOG.warning("精排返回的编号越界：%d", idx)
        return None

    meta = {
        "oneline": str(obj.get("oneline") or "").strip()[:200],
        "why": str(obj.get("why") or "").strip()[:200],
        "reason": str(obj.get("reason") or "").strip()[:160],
    }
    chosen = candidates[idx]
    LOG.info("精排选中第 %d 条：%s", idx, chosen.title[:50])
    return chosen, meta
