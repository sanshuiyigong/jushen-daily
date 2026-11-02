"""jushen-daily 主入口。

用法
    python run.py                联网抓取 → 去重 → 打分 → 渲染待读队列
    python run.py --offline      不联网，用本地库重算并重渲染（断网时也能用）
    python run.py --open         渲染完自动打开 queue.md

第 1 阶段的产物只有 reading/queue.md，还不包含卡片和推送。
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime

from engine.cardset import build_day, write_day, write_recent
from engine.config import load_config, paths
from engine.curriculum import Curriculum
from engine.fetch import fetch_all
from engine.llm import LLMClient
from engine.push import push_daily
from engine.rank import score_items
from engine.render import render_queue, write_queue
from engine.store import SeenStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run.py", description="具身日报：抓取 → 打分 → 队列")
    parser.add_argument("--offline", action="store_true", help="不联网，从本地库重算")
    parser.add_argument("--open", action="store_true", help="渲染完自动打开")
    parser.add_argument("--no-llm", action="store_true", help="强制走模板，不调 LLM")
    parser.add_argument("--no-push", action="store_true", help="不推送到手机")
    parser.add_argument("--force-push", action="store_true", help="今天推过了也重发一条")
    parser.add_argument("--if-missing", action="store_true",
                        help="今天已经生成过就直接退出（给定时任务用，避免重复跑）")
    parser.add_argument("--verbose", action="store_true", help="打印调试日志")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
        stream=sys.stdout,
    )

    cfg = load_config()
    p = paths(cfg)
    store = SeenStore(p["data"] / "seen.db")
    day = datetime.now().strftime("%Y-%m-%d")

    if args.if_missing:
        already = p["output"] / "days" / f"day-{day}.json"
        if already.exists():
            logging.info("今天（%s）已经生成过，跳过。", day)
            return 0

    if args.offline:
        items = store.load_items()
        new_count = len(items)
        logging.info("离线模式：从库中读回 %d 条", new_count)
    else:
        raw = fetch_all(cfg)
        items = store.filter_new(raw)
        new_count = len(items)
        logging.info("抓到 %d 条，其中首次出现 %d 条", len(raw), new_count)

    if not items:
        logging.info("没有新内容。仍会用库中数据重新渲染一次。")
        items = store.load_items()

    ranked = score_items(items, cfg)
    if not args.offline:
        store.save(ranked)

    ranking = cfg.get("ranking") or {}
    md = render_queue(
        ranked,
        day=day,
        threshold_mobile=float(ranking.get("mobile_threshold", 7.0)),
        threshold_pc=float(ranking.get("pc_threshold", 5.0)),
        new_count=new_count if not args.offline else len(ranked),
        offline=args.offline,
    )
    out_path = write_queue(md, p["reading"], day)

    general = cfg.get("general") or {}

    llm = LLMClient(cfg)
    if args.no_llm:
        llm.api_key = ""
    if llm.available:
        logging.info("LLM 已启用（%s）", llm.model)
    else:
        logging.info("LLM 未启用，卡片走模板降级路径")

    cur = Curriculum(p["curriculum"], p["data"] / "progress.json")
    advanced = cur.auto_advance(day)
    if advanced:
        logging.info("课程推进：%s", ", ".join(advanced))

    day_data = build_day(ranked, cfg, day, llm=llm, curriculum=cur)
    node = day_data.get("node") or {}
    if node.get("node_id"):
        cur.start(str(node["node_id"]), day)

    day_path = write_day(p["output"], day_data)
    recent_path = write_recent(p["output"], int(general.get("mobile_retention_days", 7)))

    top = ranked[0] if ranked else None
    counts = day_data.get("counts") or {}

    pushed = False
    if not args.no_push:
        try:
            pushed = push_daily(cfg, day_data, p["data"], force=args.force_push)
        except Exception as exc:  # noqa: BLE001
            logging.warning("推送出错（不影响其他部分）：%s", exc)

    print()
    print("=" * 66)
    print(f"  电脑端队列: {out_path}")
    print(f"  手机端数据: {recent_path}")
    print(f"  卡片: 概念 {counts.get('concept', 0)} · 题 {counts.get('quiz', 0)} "
          f"· 前沿 {counts.get('frontier', 0)}    （{'LLM' if day_data.get('llm') else '模板'}）")
    if node.get("title"):
        print(f"  今日概念: {node.get('track_label')} · {node.get('title')}")
    frontier_cards = [c for c in day_data.get("cards", []) if c.get("kind") == "frontier"]
    if frontier_cards:
        f0 = frontier_cards[0]
        print(f"  今日前沿: [{f0.get('score', 0):.2f}] {str(f0.get('title', ''))[:46]}")
        if f0.get("reason"):
            print(f"  选它的理由: {f0['reason']}")
    print(f"  今日新增 {new_count} 条，库总计 {store.stats()['total']} 条")
    if llm.available:
        print(f"  LLM 调用 {llm.calls} 次")
    push_cfg = cfg.get("push") or {}
    if str(push_cfg.get("channel") or "off").lower() in ("", "off", "none", "false"):
        print("  推送: 未启用")
    else:
        print(f"  推送: {'已发送到手机 ✓' if pushed else '今天已推过，跳过（--force-push 重发）'}")
    print("=" * 66)

    if args.open and out_path.exists():
        try:
            os.startfile(out_path)  # noqa: S606  (Windows 专用)
        except Exception:
            subprocess.run(["notepad", str(out_path)], check=False)  # noqa: S607
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
