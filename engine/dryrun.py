"""试跑对比：用当前配置重算历史数据，看推荐结果怎么变。

为什么需要它：
    改 config.yaml 里的关键词权重、阈值、源开关之后，只看数字是没有感觉的。
    等到第二天早上推送才知道改对没改对，太慢。
    这个工具用库里已有的历史数据（每条都存着当时的分数）重算一遍，
    立刻显示「以前会推的」和「现在会推的」差在哪。

用法：
    python -m engine.dryrun                对比全部历史
    python -m engine.dryrun --days 14      只看最近 14 天
    python -m engine.dryrun --top 12       只看前 12 名
    python -m engine.dryrun --threshold    临时试一个阈值（不改配置）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .config import load_config, paths
from .models import Item
from .rank import score_items
from .store import SeenStore

TRACK_LABEL = {"perception": "感知", "control": "控制", "general": "通用"}


def _short(text: str, n: int = 62) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _key_of(item: Item) -> str:
    return item.key


def compare(
    items: list[Item],
    cfg: dict[str, Any],
    *,
    top: int = 15,
    mobile_threshold: float | None = None,
    pc_threshold: float | None = None,
) -> dict[str, Any]:
    """返回对比结果。不打印，方便以后给聊天窗口直接调用。"""
    ranking = cfg.get("ranking") or {}

    # 「旧」用 config.yaml 里的原阈值，「新」用命令行覆盖后的阈值。
    # 这样既能在改了权重之后比（阈值不变、分数变），也能在试阈值时比（分数不变、阈值变）。
    th_old_mobile = float(ranking.get("mobile_threshold", 7.0))
    th_old_pc = float(ranking.get("pc_threshold", 5.0))
    th_mobile = float(mobile_threshold if mobile_threshold is not None else th_old_mobile)
    th_pc = float(pc_threshold if pc_threshold is not None else th_old_pc)

    old_scores = {_key_of(it): float(it.score or 0.0) for it in items}
    baseline = sorted(items, key=lambda x: -old_scores[_key_of(x)])

    rescored = score_items(items, cfg)
    new_scores = {_key_of(it): float(it.score or 0.0) for it in rescored}

    old_mobile = [it for it in baseline if old_scores[_key_of(it)] >= th_old_mobile]
    new_mobile = [it for it in rescored if new_scores[_key_of(it)] >= th_mobile]
    old_pc = [it for it in baseline if old_scores[_key_of(it)] >= th_old_pc]
    new_pc = [it for it in rescored if new_scores[_key_of(it)] >= th_pc]

    old_ids = {_key_of(it) for it in old_pc}
    new_ids = {_key_of(it) for it in new_pc}

    entered = [it for it in new_pc if _key_of(it) not in old_ids]
    left = [it for it in old_pc if _key_of(it) not in new_ids]

    moved = []
    old_pos = {_key_of(it): i + 1 for i, it in enumerate(baseline)}
    for i, it in enumerate(rescored[:top]):
        k = _key_of(it)
        before = old_pos.get(k, 999)
        if before != i + 1:
            moved.append((it, before, i + 1, old_scores.get(k, 0.0), new_scores[k]))

    return {
        "total": len(items),
        "thresholds": {"mobile": th_mobile, "pc": th_pc},
        "thresholds_old": {"mobile": th_old_mobile, "pc": th_old_pc},
        "old_mobile_count": len(old_mobile),
        "new_mobile_count": len(new_mobile),
        "old_pc_count": len(old_pc),
        "new_pc_count": len(new_pc),
        "entered": entered[:8],
        "left": left[:8],
        "top_new": rescored[:top],
        "moved": moved[:10],
        "old_scores": old_scores,
        "new_scores": new_scores,
    }


def render(result: dict[str, Any]) -> str:
    lines: list[str] = []
    th = result["thresholds"]
    old_th = result.get("thresholds_old") or th

    def _th(old: float, new: float) -> str:
        return f"{old} → {new}" if old != new else f"{new}"

    lines.append(
        f"样本 {result['total']} 条   "
        f"手机阈值 {_th(old_th['mobile'], th['mobile'])}   "
        f"电脑阈值 {_th(old_th['pc'], th['pc'])}"
    )
    lines.append("")
    lines.append(f"手机级  {result['old_mobile_count']:>3} 条  →  {result['new_mobile_count']:>3} 条")
    lines.append(f"电脑级  {result['old_pc_count']:>3} 条  →  {result['new_pc_count']:>3} 条")

    if result["entered"]:
        lines.append("")
        lines.append("▲ 新进榜")
        for it in result["entered"]:
            lines.append(f"   {it.score:5.2f}  {_short(it.title)}")

    if result["left"]:
        lines.append("")
        lines.append("▼ 掉出榜")
        for it in result["left"]:
            old = result["old_scores"].get(it.key, 0)
            new = result["new_scores"].get(it.key, 0)
            lines.append(f"   {old:5.2f} → {new:5.2f}  {_short(it.title)}")

    if result["moved"]:
        lines.append("")
        lines.append("↕ 名次变化（前 15 内）")
        for it, before, after, old_s, new_s in result["moved"]:
            arrow = "↑" if after < before else "↓"
            lines.append(f"   {arrow} #{before} → #{after}   {new_s:5.2f}  {_short(it.title, 50)}")

    lines.append("")
    lines.append("现在的前 15 名：")
    for i, it in enumerate(result["top_new"], 1):
        track = TRACK_LABEL.get(str(it.score_parts.get("track", "general")), "?")
        lines.append(f"   {i:>2}. {it.score:5.2f} [{track}] {_short(it.title, 56)}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="engine.dryrun", description="用当前配置重算历史，对比推荐结果")
    parser.add_argument("--days", type=int, default=None, help="只看最近 N 天入库的条目")
    parser.add_argument("--top", type=int, default=15, help="显示前 N 名（默认 15）")
    parser.add_argument("--mobile", type=float, default=None, help="临时覆盖手机阈值来试")
    parser.add_argument("--pc", type=float, default=None, help="临时覆盖电脑阈值来试")
    args = parser.parse_args(argv)

    cfg = load_config()
    p = paths(cfg)
    store = SeenStore(p["data"] / "seen.db")
    items = store.load_items(days=args.days)
    if not items:
        print(f"库里没有数据。先跑一次 run.py 抓点东西进来。")
        return 1

    result = compare(
        items, cfg, top=args.top,
        mobile_threshold=args.mobile, pc_threshold=args.pc,
    )
    print()
    print("=" * 68)
    print(render(result))
    print("=" * 68)
    if args.mobile is None and args.pc is None:
        print("\n（这是用 config.yaml 当前配置算的。改完配置再跑一次就能看到差别）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
