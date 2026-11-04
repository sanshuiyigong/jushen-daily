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

from engine.archive import append_day
from engine.cardset import build_day, write_day, write_recent
from engine.clock import today as today_bj
from engine.config import load_config, paths
from engine.curriculum import Curriculum
from engine.fetch import fetch_all
from engine.llm import LLMClient
from engine.models import Item
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
    # 必须用北京时间：云端是 UTC，早 7:30 的定时在 UTC 还是前一天
    day = today_bj()

    if args.if_missing:
        # 两个判据：
        #   1. output/days 里有今天的文件（本机跑过）
        #   2. 归档里有今天的卡片（云端跑过，且已随 git pull 同步下来）
        # 第二个判据是关键——output 不进仓库，但 data/archive 进，所以它能
        # 告诉本机「云端今天已经做过了，别重复花钱」。
        already = p["output"] / "days" / f"day-{day}.json"
        if already.exists():
            logging.info("今天（%s）本地已经生成过，跳过。", day)
            return 0
        try:
            from engine.archive import iter_cards

            if any(str(c.get("day")) == day for c in iter_cards(p["data"])):
                logging.info("今天（%s）云端已经生成并归档，跳过。", day)
                return 0
        except Exception:  # noqa: BLE001
            pass

    if args.offline:
        items = store.load_items()
        new_count = len(items)
        logging.info("离线模式：从库中读回 %d 条", new_count)
    else:
        raw = fetch_all(cfg)
        fresh = store.filter_new(raw)
        # 候选池 = 今天新抓到的 ∪ 最近 N 天抓到但**从没被推过**的。
        # 只取新的会让第二天池子干涸——昨天输给强手的论文今天本该继续竞争。
        pending = store.pending(days=int((cfg.get("general") or {}).get("candidate_days", 14)))
        merged: dict[str, Item] = {it.key: it for it in pending}
        for it in fresh:
            merged[it.key] = it          # 新抓到的信息更新，覆盖旧的
        items = list(merged.values())
        new_count = len(fresh)
        logging.info(
            "抓到 %d 条（首次出现 %d 条），加上没推过的旧候选 %d 条 → 候选池 %d 条",
            len(raw), len(fresh), len(pending), len(items),
        )

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

    # 追加进长期归档 data/archive/YYYY-MM.jsonl —— 这是唯一能一直往后翻的地方
    try:
        archived = append_day(p["data"], day_data)
    except Exception as exc:  # noqa: BLE001
        logging.warning("归档失败（不影响今天的内容）：%s", exc)
        archived = 0

    top = ranked[0] if ranked else None
    counts = day_data.get("counts") or {}

    pushed = False
    if not args.no_push:
        try:
            pushed = push_daily(cfg, day_data, p["data"], force=args.force_push)
        except Exception as exc:  # noqa: BLE001
            logging.warning("推送出错（不影响其他部分）：%s", exc)

    # 真的推出去了，才把这条前沿标记为已推 —— 明天不再重复推同一条。
    # 用 day_data 里记的 picked_key，而不是"所有过线的条目"，
    # 因为只有被选中的那一条真正到过手机上。
    picked_key = str(day_data.get("picked_key") or "")
    if pushed and picked_key:
        try:
            store.mark_pushed([picked_key])
        except Exception as exc:  # noqa: BLE001
            logging.warning("标记已推失败：%s", exc)

    print()
    print("=" * 66)
    print(f"  电脑端队列: {out_path}")
    print(f"  手机端数据: {recent_path}")
    print(f"  卡片: 概念 {counts.get('concept', 0)} · 题 {counts.get('quiz', 0)} "
          f"· 前沿 {counts.get('frontier', 0)}    （{'LLM' if day_data.get('llm') else '模板'}）")
    if node.get("title"):
        print(f"  今日概念: {node.get('track_label')} · {node.get('title')}")
    if archived:
        print(f"  归档: 新增 {archived} 张 → data/archive/{day[:7]}.jsonl")
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
