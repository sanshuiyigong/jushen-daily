"""卡片生成：有 LLM 就精修，没 LLM 就退化成模板。

三种卡
  concept   概念卡 —— 来自课程骨架，LLM 展开成 200 多字的讲解
  quiz      题卡   —— 围绕当天概念，LLM 出选择题 + 解析
  frontier  前沿卡 —— 来自当天打分结果，LLM 写一句「和你什么关系」

任何一步 LLM 失败都只是「退化成模板」，不会让整条链路挂掉。
"""

from __future__ import annotations

import logging
from typing import Any

from .llm import LLMClient
from .models import Item

LOG = logging.getLogger("card")

SYS_TUTOR = (
    "你是一位具身智能方向的助教，正在给一个大二学生写每日学习卡片。"
    "这个学生的背景：视觉方面有一定基础（拿过工创赛省奖，在一家做具身的初创公司"
    "负责视觉模块和上位机控制），但电控刚入门；目标是从事具身智能与机器人感知。"
    "写作要求：准确、具体、不说空话；能用真实机器人上的现象举例就用例子；"
    "不要用「总而言之」「综上所述」这类填充。"
)

SYS_VERIFY = (
    "你是一位极其严格的审题人，专门检查物理和数学题目里的错误答案。"
    "你的唯一任务是找出「标注的答案在物理上不成立」的题，并给出正确答案。"
    "如果一道题原本就是对的，就不要动它。宁可放过，不可改错。"
)


def _clip(text: Any, limit: int = 300) -> str:
    s = str(text or "").strip()
    return s if len(s) <= limit else s[:limit].rstrip() + "…"


def _reading_lines(node: dict[str, Any]) -> str:
    rows = []
    for rd in node.get("reading") or []:
        title = rd.get("title") if isinstance(rd, dict) else str(rd)
        if title:
            rows.append(f"- {title}")
    return "\n".join(rows)


def _checkpoint_lines(node: dict[str, Any]) -> str:
    rows = []
    for cp in node.get("checkpoints") or []:
        rows.append(f"- {cp}")
    return "\n".join(rows)


def _verify_quizzes(cards: list[dict[str, Any]], llm: LLMClient) -> tuple[list[dict[str, Any]], int]:
    """第二道工序：让模型自己复核答案，纠正物理上站不住的选项。

    为什么必须有这一步：实测生成过一道题，「fx 增大 10% 图像会怎样」，
    模型标了「整体放大，但水平方向放大更多」，而正确答案是「只有水平方向被拉伸」。
    一道错题比没有题更糟，所以宁可多花一次调用。
    """
    import json as _json

    payload = _json.dumps(
        [
            {
                "i": i,
                "question": c["question"],
                "options": c["options"],
                "marked_answer": c["answer"],
                "explain": c.get("explain", ""),
            }
            for i, c in enumerate(cards)
        ],
        ensure_ascii=False,
        indent=1,
    )
    user = f"""下面是刚生成的 {len(cards)} 道单选题，标注的答案都可能是错的。
请逐题核对：标注答案是否在物理/数学上严格成立？有没有另一个选项明显更正确？

{payload}

输出 JSON：
{{"fixes": [{{"i": 题目编号, "answer": 正确的选项编号, "explain": "重写后的解析，80 字以内"}}]}}

只列出需要修改的题。如果全部正确，返回 {{"fixes": []}}。"""

    obj = llm.chat_json(SYS_VERIFY, user, temperature=0.1, max_tokens=900)
    if not obj:
        return cards, 0
    fixes = obj.get("fixes") or []
    changed = 0
    for fix in fixes:
        try:
            i = int(fix.get("i", -1))
            ans = int(fix.get("answer", -1))
        except (TypeError, ValueError):
            continue
        if not 0 <= i < len(cards):
            continue
        if not 0 <= ans < len(cards[i]["options"]):
            continue
        if cards[i]["answer"] != ans:
            changed += 1
            LOG.warning(
                "答案纠错：题%d 「%s」 %s → %s",
                i + 1,
                cards[i]["question"][:30],
                cards[i]["answer"],
                ans,
            )
        cards[i]["answer"] = ans
        if fix.get("explain"):
            cards[i]["explain"] = _clip(fix["explain"], 260)
    return cards, changed


# ------------------------------------------------------------------ 概念卡
def concept_card(
    node: dict[str, Any],
    track_label: str,
    day: str,
    llm: LLMClient | None = None,
) -> dict[str, Any]:
    node_id = node["id"]
    card: dict[str, Any] = {
        "kind": "concept",
        "id": f"c-{node_id}",
        "day": day,
        "node_id": node_id,
        "track": track_label,
        "title": node.get("title", ""),
        "body": "",
        "analogy": "",
        "misconception": "",
        "checkpoints": node.get("checkpoints") or [],
        "reading": node.get("reading") or [],
        "mode": "template",
    }

    if llm and llm.available:
        user = f"""课程节点：{node.get('title')}
所属轨道：{track_label}
学习目标：{node.get('goal')}
前置节点：{node.get('prereq') or '无'}
原始材料：
{_reading_lines(node)}
检验点：
{_checkpoint_lines(node)}

请输出 JSON，三个字段：
{{"body": "200-280 字，分 3 段，段与段之间用 \\n\\n 分隔。第一段讲它到底是什么（定义 + 关键式子）；第二段讲它在真实机器人上会表现成什么现象；第三段讲最容易踩的坑。",
 "analogy": "一个生活化的类比，30 字以内",
 "misconception": "初学者最常见的误解，40 字以内"}}"""
        obj = llm.chat_json(SYS_TUTOR, user, temperature=0.5, max_tokens=900)
        if obj and obj.get("body"):
            card["body"] = _clip(obj.get("body"), 900)
            card["analogy"] = _clip(obj.get("analogy"), 120)
            card["misconception"] = _clip(obj.get("misconception"), 160)
            card["mode"] = "llm"
        else:
            LOG.warning("概念卡 LLM 失败，退回模板：%s", node_id)

    if not card["body"]:
        lines = [f"目标：{node.get('goal')}"]
        lines.append("")
        lines.append(f"这是「{track_label}」线的第 {node.get('order')} 格。")
        prereq = node.get("prereq") or []
        if prereq:
            lines.append(f"前置：{', '.join(prereq)}")
        lines.append("")
        lines.append("学完你应该能做到：")
        for cp in node.get("checkpoints") or []:
            lines.append(f"· {cp}")
        card["body"] = "\n".join(lines)
        card["mode"] = "template"

    return card


# -------------------------------------------------------------------- 题卡
def quiz_cards(
    node: dict[str, Any],
    day: str,
    limit: int = 2,
    llm: LLMClient | None = None,
) -> list[dict[str, Any]]:
    node_id = node["id"]
    cards: list[dict[str, Any]] = []

    if llm and llm.available:
        user = f"""基于下面这个概念，出 {limit} 道单选题。

概念：{node.get('title')}
目标：{node.get('goal')}
检验点：
{_checkpoint_lines(node)}

要求：
- 每题 4 个选项，只有 1 个正确
- 考理解，不考记忆
- 错误选项要是「看起来合理、但实际会踩的坑」
- 解析要说清为什么那个错的最容易选

输出 JSON：
{{"questions": [{{"question": "题干", "options": ["选项1","选项2","选项3","选项4"],
   "answer": 0, "explain": "一句解析，60 字以内"}}]}}"""
        obj = llm.chat_json(SYS_TUTOR, user, temperature=0.6, max_tokens=1200)
        questions = (obj or {}).get("questions") or []
        for idx, q in enumerate(questions[:limit]):
            options = [str(o) for o in (q.get("options") or [])]
            if len(options) < 2 or not q.get("question"):
                continue
            try:
                answer = int(q.get("answer", 0))
            except (TypeError, ValueError):
                answer = 0
            if not 0 <= answer < len(options):
                answer = 0
            cards.append(
                {
                    "kind": "quiz",
                    "id": f"q-{node_id}-{idx + 1}",
                    "day": day,
                    "node_id": node_id,
                    "question": str(q.get("question")),
                    "options": options,
                    "answer": answer,
                    "explain": _clip(q.get("explain"), 240),
                    "mode": "llm",
                }
            )
        if cards:
            try:
                cards, changed = _verify_quizzes(cards, llm)
                if changed:
                    LOG.info("复核修正了 %d 道题的答案", changed)
                else:
                    LOG.info("复核通过，答案无需修正")
            except Exception as exc:  # noqa: BLE001
                LOG.warning("题卡复核出错，保留原答案：%s", exc)
            return cards
        LOG.warning("题卡 LLM 失败，退回自检卡：%s", node_id)

    # 退化：把每条检验点变成一张「你能做到吗」的自检卡
    for idx, cp in enumerate((node.get("checkpoints") or [])[:limit]):
        cards.append(
            {
                "kind": "quiz",
                "id": f"q-{node_id}-self-{idx + 1}",
                "day": day,
                "node_id": node_id,
                "question": f"你现在能做到吗？\n{cp}",
                "options": ["做到过，也能讲清楚", "大概懂，但讲不顺", "还不行"],
                "answer": 0,
                "explain": "检验点是用来做的，不是用来背的。做不到就回到原始材料，"
                "找一个真实场景自己推一遍。",
                "mode": "selfcheck",
            }
        )
    return cards


# ------------------------------------------------------------------ 前沿卡
def frontier_card(
    item: Item,
    day: str,
    llm: LLMClient | None = None,
    track_hint: str = "",
    *,
    oneline_override: str = "",
    why_override: str = "",
) -> dict[str, Any]:
    extra = item.extra
    links: dict[str, str] = {}
    if extra.get("arxiv_id"):
        links["arxiv"] = f"https://arxiv.org/abs/{extra['arxiv_id']}"
    if extra.get("pdf"):
        links["pdf"] = extra["pdf"]
    if extra.get("github"):
        links["code"] = extra["github"]
    if extra.get("project"):
        links["project"] = extra["project"]
    if not links:
        links["origin"] = item.url

    summary = str(item.summary or "").strip()
    oneline = oneline_override or (
        summary if len(summary) <= 150 else summary[:147].rstrip() + "…"
    )

    why = why_override or f"和你正在推进的{track_hint or '具身'}线相关"
    if not why_override and llm and llm.available:
        user = f"""这篇论文/项目：
标题：{item.title}
摘要：{summary[:900]}

请用一句话（40 字以内）说明它和一个正在学「{track_hint or '具身智能'}」的大二学生有什么关系。
输出 JSON：{{"why": "..."}}"""
        obj = llm.chat_json(SYS_TUTOR, user, temperature=0.4, max_tokens=200)
        if obj and obj.get("why"):
            why = _clip(obj["why"], 90)

    return {
        "kind": "frontier",
        "id": f"f-{item.key}",
        "day": day,
        "title": item.title,
        "oneline": oneline,
        "why": why,
        "score": item.score,
        "track": track_hint or str(item.score_parts.get("track", "general")),
        "links": links,
        "mode": "llm" if (why_override or oneline_override or (llm and llm.available)) else "template",
    }
