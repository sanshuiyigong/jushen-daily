"""卡片归档：把每天生成的卡片追加进按月切分的 JSONL。

为什么需要它：
    之前只有 output/days/*.json，而那是「今天的工作区」——手机端只读最近 7 天，
    云端更是每次 Actions 跑完就丢。结果就是：三个月前的一张卡片找不回来。

为什么用 JSONL 而不是数据库或 JSON 数组：
    · 追加写：一次崩溃不会毁掉整个文件（JSON 数组则要重写全文）
    · 一行一张卡：grep 直接能搜，不依赖任何工具
    · git 友好：只增加行，几乎不冲突；一年不到 1 MB
    · 幂等：同一个 (day, id) 不会重复写入，重复跑安全

文件布局：
    data/archive/2026-11.jsonl
    data/archive/2026-12.jsonl
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .clock import stamp as stamp_bj
from .clock import today as today_bj

LOG = logging.getLogger("archive")

DIR_NAME = "archive"

# 用户可能怎么输日期
_RE_FULL = re.compile(r"^\d{4}-\d{2}-\d{2}$")     # 2026-11-03
_RE_MONTH = re.compile(r"^\d{4}-\d{2}$")          # 2026-11
_RE_MMDD = re.compile(r"^\d{1,2}-\d{1,2}$")       # 11-03
_RE_COMPACT = re.compile(r"^\d{8}$")              # 20261103


def archive_dir(data_dir: Path) -> Path:
    path = Path(data_dir) / DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def month_file(data_dir: Path, day: str) -> Path:
    month = (day or "")[:7] or today_bj()[:7]
    return archive_dir(data_dir) / f"{month}.jsonl"


def _iter_file(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue  # 坏行直接跳过，不影响其他行
            if isinstance(obj, dict):
                yield obj


def append_day(data_dir: Path, day_data: dict[str, Any]) -> int:
    """把一天的卡片追加进归档。已存在的 (day, id) 不会重复写。返回新写入条数。"""
    day = str(day_data.get("day") or today_bj())
    cards = day_data.get("cards") or []
    if not cards:
        return 0

    path = month_file(data_dir, day)
    seen = {str(c.get("id")) for c in _iter_file(path) if str(c.get("day")) == day}

    fresh: list[str] = []
    for card in cards:
        cid = str(card.get("id") or "")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        record = dict(card)
        record["day"] = day
        record["archived_at"] = stamp_bj()
        fresh.append(json.dumps(record, ensure_ascii=False))

    if not fresh:
        return 0

    with open(path, "a", encoding="utf-8") as fh:
        for line in fresh:
            fh.write(line + "\n")
    LOG.info("归档 %d 张卡片 → %s", len(fresh), path.name)
    return len(fresh)


def iter_cards(
    data_dir: Path,
    *,
    since: str | None = None,
    until: str | None = None,
) -> Iterator[dict[str, Any]]:
    """按时间顺序遍历所有归档卡片。"""
    root = Path(data_dir) / DIR_NAME
    if not root.exists():
        return
    for path in sorted(root.glob("*.jsonl")):
        for card in _iter_file(path):
            day = str(card.get("day") or "")
            if since and day < since:
                continue
            if until and day > until:
                continue
            yield card


_KIND_LABEL = {"concept": "概念", "quiz": "题", "frontier": "前沿"}


def days_index(data_dir: Path) -> list[dict[str, Any]]:
    """按天汇总，给界面画时间线用。新的在前。"""
    buckets: dict[str, dict[str, int]] = {}
    for card in iter_cards(data_dir):
        day = str(card.get("day") or "")
        if not day:
            continue
        b = buckets.setdefault(day, {"concept": 0, "quiz": 0, "frontier": 0})
        kind = str(card.get("kind") or "")
        if kind in b:
            b[kind] += 1
    out = [{"day": d, **v, "total": sum(v.values())} for d, v in buckets.items()]
    out.sort(key=lambda x: x["day"], reverse=True)
    return out


def query(data_dir: Path, q: str = "", *, limit: int = 60) -> dict[str, Any]:
    """一个入口处理「按日期」和「按关键词」两种查法。

    输入看起来像日期就按日期查（支持 2026-11-03 / 2026-11 / 11-03 / 20261103），
    否则在当前月里做关键词搜索。返回的 cards 按时间正序，方便阅读。
    """
    text = (q or "").strip()

    if not text:
        cards = list(iter_cards(data_dir))[-limit:]
        return {"mode": "recent", "label": "最近归档", "count": len(cards), "cards": cards}

    # 20261103 → 2026-11-03
    if _RE_COMPACT.match(text):
        text_date = f"{text[:4]}-{text[4:6]}-{text[6:]}"
        cards = [c for c in iter_cards(data_dir) if str(c.get("day")) == text_date]
        return {"mode": "day", "label": text_date, "count": len(cards), "cards": cards}

    if _RE_FULL.match(text):
        cards = [c for c in iter_cards(data_dir) if str(c.get("day")) == text]
        return {"mode": "day", "label": text, "count": len(cards), "cards": cards}

    if _RE_MONTH.match(text):
        cards = [c for c in iter_cards(data_dir) if str(c.get("day", "")).startswith(text)]
        return {"mode": "month", "label": text, "count": len(cards), "cards": cards}

    if _RE_MMDD.match(text):
        mm, dd = text.split("-")
        suffix = f"-{int(mm):02d}-{int(dd):02d}"
        cards = [c for c in iter_cards(data_dir) if str(c.get("day", "")).endswith(suffix)]
        return {"mode": "day", "label": suffix.strip("-"), "count": len(cards), "cards": cards}

    hits = search(data_dir, text, limit=limit)
    return {"mode": "keyword", "label": text, "count": len(hits), "cards": hits}


def _card_text(card: dict[str, Any]) -> str:
    parts = [
        str(card.get("title") or ""),
        str(card.get("title_zh") or ""),
        str(card.get("body") or ""),
        str(card.get("question") or ""),
        str(card.get("oneline") or ""),
        str(card.get("why") or ""),
        str(card.get("explain") or ""),
    ]
    parts.extend(str(o) for o in (card.get("options") or []))
    return " ".join(parts)


def search(
    data_dir: Path,
    keyword: str,
    *,
    limit: int = 20,
    kinds: set[str] | None = None,
) -> list[dict[str, Any]]:
    """在归档里搜关键词（标题、正文、题干、选项、解析都会查）。"""
    kw = keyword.strip().lower()
    if not kw:
        return []
    hits: list[dict[str, Any]] = []
    for card in iter_cards(data_dir):
        if kinds and str(card.get("kind")) not in kinds:
            continue
        if kw in _card_text(card).lower():
            hits.append(card)
    return hits[-limit:]


def stats(data_dir: Path) -> dict[str, Any]:
    """归档概况：文件数、卡片数、覆盖天数、体积。"""
    root = Path(data_dir) / DIR_NAME
    if not root.exists():
        return {"files": 0, "cards": 0, "days": 0, "bytes": 0, "first": "", "last": ""}

    files = sorted(root.glob("*.jsonl"))
    total = 0
    days: set[str] = set()
    size = 0
    for path in files:
        size += path.stat().st_size
        for card in _iter_file(path):
            total += 1
            if card.get("day"):
                days.add(str(card["day"]))

    ordered = sorted(days)
    return {
        "files": len(files),
        "cards": total,
        "days": len(days),
        "bytes": size,
        "first": ordered[0] if ordered else "",
        "last": ordered[-1] if ordered else "",
    }


# ------------------------------------------------------------------ CLI


def _print_card(card: dict[str, Any]) -> None:
    kind = _KIND_LABEL.get(str(card.get("kind")), str(card.get("kind")))
    print()
    print(f"  [{kind}] {card.get('day')}")
    title = card.get("title_zh") or card.get("title") or card.get("question") or ""
    print(f"  {title}")
    if card.get("title_zh") and card.get("title"):
        print(f"  （{card['title']}）")
    body = card.get("body")
    if body:
        for line in str(body).split("\n"):
            if line.strip():
                print(f"    {line}")
    opts = card.get("options") or []
    if opts:
        letters = "ABCDEF"
        for i, opt in enumerate(opts):
            mark = " ✔" if i == card.get("answer") else ""
            print(f"    {letters[i] if i < len(letters) else i}. {opt}{mark}")
    for key, label in (("explain", "解析"), ("oneline", "一句"), ("why", "为什么")):
        if card.get(key):
            print(f"    {label}：{card[key]}")
    if card.get("score") is not None:
        print(f"    分数：{card['score']}")


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    from .config import load_config, paths

    parser = argparse.ArgumentParser(prog="engine.archive", description="卡片归档：统计 / 搜索 / 回看")
    parser.add_argument("--search", "-s", default="", help="按关键词搜")
    parser.add_argument("--day", default="", help="看某一天的全部卡片，如 2026-11-03")
    parser.add_argument("--kind", default="", help="只看某一类：concept / quiz / frontier")
    parser.add_argument("--limit", type=int, default=20, help="最多显示几条（默认 20）")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s", stream=sys.stdout)
    cfg = load_config()
    p = paths(cfg)
    data_dir = p["data"]

    s = stats(data_dir)
    print()
    print("=" * 66)
    print(f"  归档：{s['cards']} 张卡片 / {s['days']} 天 / {s['files']} 个文件 / {s['bytes'] / 1024:.0f} KB")
    if s["first"]:
        print(f"  覆盖：{s['first']} → {s['last']}")
    print("=" * 66)

    if args.search:
        hits = search(data_dir, args.search, limit=args.limit,
                      kinds={args.kind} if args.kind else None)
        print(f"\n搜「{args.search}」：命中 {len(hits)} 条")
        for card in hits:
            _print_card(card)
        return 0

    if args.day:
        found = [c for c in iter_cards(data_dir) if str(c.get("day")) == args.day]
        print(f"\n{args.day}：{len(found)} 张卡片")
        for card in found:
            _print_card(card)
        return 0

    if s["cards"]:
        print(f"\n最近的几张（--search 关键词 可以搜全部，--day 2026-11-03 看某天）")
        for card in list(iter_cards(data_dir))[-6:]:
            _print_card(card)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
