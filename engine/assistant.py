"""聊天调参助手。

流程：
    用户说人话 → LLM 输出结构化补丁 → 服务端先校验能不能应用
    → 前端展示 diff → 用户点「应用」才真的写文件 → 自动 git commit

关键设计：**模型没有写文件的能力。**
它只能返回 {file, old, new} 这样的文本替换提议，写不写由人决定。
这不是不信任模型，是因为配置错一次会错很多天——内容错了只错那一天。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .llm import LLMClient
from .patcher import (
    ALLOWED_FILES,
    PatchError,
    config_summary,
    curriculum_summary,
    validate_patch,
)

LOG = logging.getLogger("assistant")

MAX_HISTORY = 6

SYS = """你在帮陈江调整他自建的「具身日报」项目的配置。

这个项目每天抓取具身智能/机器人感知领域的新内容，打分筛选，生成概念卡、自测题和前沿卡，
推到他的手机。他大二，视觉有一定基础（拿过工创赛省奖，在初创公司做视觉模块和上位机），
电控刚入门，目标是具身智能与机器人感知。

你的任务是：把他的话翻译成对配置文件的**精确文本替换**。

硬规则：
1. 只能改这三个文件：config.yaml / curriculum/perception.yaml / curriculum/control.yaml
2. 每个补丁给 old 和 new。old 必须和文件里的内容**逐字符一致**（包括缩进、冒号后的空格），
   并且在整个文件里**只能出现一次**。缩进不对就直接失败，所以抄的时候必须一模一样。
3. 改动要小。一次只改 1-3 个地方，不要顺手"优化"别的参数。
4. 用户只是提问、不需要改配置时，patches 返回空数组，正常回答。
5. 不确定该改哪个值时，先在 reply 里说清楚你的建议和理由，patches 给空，等他确认。

只输出 JSON，格式：
{"reply": "1-3 句话，说清你改了什么、为什么",
 "patches": [{"file": "config.yaml", "old": "原样文本", "new": "替换后文本", "reason": "一句话"}]}
"""


def _build_prompt(root: Path) -> str:
    """把模型需要看的上下文拼起来。"""
    cfg_text = (Path(root) / "config.yaml").read_text(encoding="utf-8")
    return "\n\n".join(
        [
            "# 当前 config.yaml 全文（改的时候要照着它的缩进抄）",
            "```yaml",
            cfg_text,
            "```",
            "# 配置摘要（方便你快速定位）",
            config_summary(root),
            "# 课程骨架",
            curriculum_summary(root),
            "# 允许改动的文件",
            ", ".join(sorted(ALLOWED_FILES)),
        ]
    )


def ask(
    root: Path,
    llm: LLMClient,
    message: str,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """处理一条用户消息，返回 {ok, reply, patches, error}。"""
    if not llm.available:
        return {
            "ok": False,
            "error": "没有配置 LLM key，聊天功能不可用。设置环境变量 JUSHEN_LLM_KEY 或填 config.yaml 的 llm.api_key。",
            "reply": "",
            "patches": [],
        }

    context = _build_prompt(root)
    user_parts = [context, "# 用户的话", message]
    user = "\n\n".join(user_parts)

    messages: list[dict[str, str]] = [{"role": "system", "content": SYS}]
    for turn in (history or [])[-MAX_HISTORY:]:
        role = turn.get("role")
        content = str(turn.get("content") or "")[:1500]
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user})

    text = llm.chat(messages, temperature=0.2, max_tokens=2000, json_mode=True)
    if not text:
        return {"ok": False, "error": "模型没有返回内容（网络或额度问题）", "reply": "", "patches": []}

    from .llm import _extract_json  # 复用同一套容错解析

    obj = _extract_json(text)
    if not obj:
        return {
            "ok": False,
            "error": "模型返回的不是合法 JSON",
            "reply": text[:400],
            "patches": [],
        }

    reply = str(obj.get("reply") or "").strip()
    raw_patches = obj.get("patches") or []
    patches: list[dict[str, Any]] = []

    for raw in raw_patches[:5]:
        if not isinstance(raw, dict):
            continue
        file = str(raw.get("file") or "")
        old = str(raw.get("old") or "")
        new = str(raw.get("new") or "")
        reason = str(raw.get("reason") or "")
        item: dict[str, Any] = {
            "file": file,
            "old": old,
            "new": new,
            "reason": reason,
            "applicable": False,
            "error": "",
        }
        try:
            validate_patch(Path(root), file, old, new)
            item["applicable"] = True
        except PatchError as exc:
            item["error"] = str(exc)
            LOG.info("补丁不可用：%s", exc)
        patches.append(item)

    return {"ok": True, "reply": reply, "patches": patches, "error": ""}


def apply(
    root: Path,
    file: str,
    old: str,
    new: str,
    reason: str = "",
) -> dict[str, Any]:
    """应用一个补丁。前端只会在用户点「应用」之后调到这里。"""
    from .patcher import apply_patch

    try:
        info = apply_patch(Path(root), file, old, new, reason)
    except PatchError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, **info}
