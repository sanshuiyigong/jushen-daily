"""规则打分器。

score = w_src·源权重 + w_kw·关键词命中 + w_heat·热度 + w_rec·新鲜度

两个必须做对的细节：
1. 热度按源分开归一化（HF 50 赞 ≠ GitHub 50 星）
2. 关键词用词边界匹配，不用子串（否则 'vla' 会命中 'vlan'、'grasp' 会命中 'grasping bag'）
"""

from __future__ import annotations

import math
import re
from typing import Any, Iterable

from .models import Item

DEFAULT_WEIGHTS = {"source": 0.35, "keyword": 0.35, "heat": 0.15, "recency": 0.15}

# 没有命中任何核心词时的惩罚系数
CORE_MISS_PENALTY = 0.6

TRACK_KEYWORDS = {
    "perception": [
        "vision", "slam", "vio", "calibration", "hand-eye", "pose", "point cloud",
        "depth", "segmentation", "detection", "camera", "lidar", "6d pose", "nerf",
        "gaussian splatting", "visual", "perception", "tracking",
    ],
    "control": [
        "control", "motor", "foc", "servo", "actuator", "torque", "impedance",
        "pid", "trajectory", "motion planning", "grasp", "manipulation", "dexterous",
        "force", "haptic", "kinematics", "dynamics",
    ],
}


def _hits(text: str, keywords: Iterable[str]) -> list[str]:
    """返回在 text 里以词边界命中的关键词。"""
    low = text.lower()
    found: list[str] = []
    for kw in keywords:
        word = str(kw).lower().strip()
        if not word:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", low):
            found.append(word)
    return found


def source_weight_of(source: str, weights: dict[str, float]) -> float:
    """source 形如 'arxiv:cs.RO' / 'hf_papers' / 'github:embodied-ai'，取最长前缀匹配。"""
    best, best_len = 0.0, -1
    for name, weight in weights.items():
        if source == name or source.startswith(name + ":"):
            if len(name) > best_len:
                best, best_len = float(weight), len(name)
    return best


def heat_score(item: Item, caps: dict[str, float]) -> float:
    """按源归一化的热度。没有热度信号的源给中性值 0.45。"""
    cap = caps.get(item.source.split(":")[0])
    if not cap or item.heat <= 0:
        return 0.45
    return min(1.0, math.log1p(item.heat) / math.log1p(cap))


def recency_score(age_hours: float) -> float:
    if age_hours <= 24:
        return 1.0
    if age_hours <= 72:
        return 1.0 - 0.6 * (age_hours - 24) / 48.0
    horizon = 24 * 45 - 72
    return max(0.1, 0.4 - 0.3 * (age_hours - 72) / max(horizon, 1))


def keyword_score(text: str, keywords: dict[str, float]) -> tuple[float, list[str]]:
    matched = _hits(text, keywords.keys())
    if not matched:
        return 0.0, []
    total = sum(float(keywords[m]) for m in matched)
    return min(1.0, total / 2.0), matched


def infer_track(text: str) -> str:
    scores = {track: len(_hits(text, kws)) for track, kws in TRACK_KEYWORDS.items()}
    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    return best if scores[best] > 0 else "general"


def score_items(items: Iterable[Item], cfg: dict[str, Any]) -> list[Item]:
    ranking = cfg.get("ranking") or {}
    weights = {**DEFAULT_WEIGHTS, **(ranking.get("weights") or {})}
    keywords = {k: float(v) for k, v in (ranking.get("keywords") or {}).items()}
    caps = {str(k): float(v) for k, v in (ranking.get("heat_cap") or {}).items()}
    core = [str(k) for k in (ranking.get("core") or [])]
    src_weights = {
        name: float(spec.get("weight", 0.5))
        for name, spec in (cfg.get("sources") or {}).items()
    }

    scored: list[Item] = []
    for item in items:
        text = f"{item.title} {item.summary}"
        s_src = source_weight_of(item.source, src_weights)
        s_kw, matched = keyword_score(text, keywords)
        s_heat = heat_score(item, caps)
        s_rec = recency_score(item.age_hours)

        base = (
            weights["source"] * s_src
            + weights["keyword"] * s_kw
            + weights["heat"] * s_heat
            + weights["recency"] * s_rec
        )
        # 核心词门禁：只看标题。
        # 摘要里出现 embodied 太常见（LLM 论文顺手提一句），但标题里出现
        # 才说明这篇论文真正是讲具身的。
        core_hit = bool(_hits(item.title, core)) if core else True
        if not core_hit:
            base *= CORE_MISS_PENALTY

        item.score = round(base * 10, 3)  # 对外统一 0~10 分制
        item.score_parts = {
            "source": round(s_src, 3),
            "keyword": round(s_kw, 3),
            "heat": round(s_heat, 3),
            "recency": round(s_rec, 3),
            "core": 1.0 if core_hit else 0.0,
            "matched": matched[:6],  # type: ignore[dict-item]
            "track": infer_track(text),  # type: ignore[dict-item]
        }
        scored.append(item)

    scored.sort(key=lambda x: -x.score)
    return scored


def select(items: list[Item], *, min_score: float = 0.0, limit: int | None = None) -> list[Item]:
    out = [it for it in items if it.score >= min_score]
    return out[:limit] if limit else out


if __name__ == "__main__":
    import logging
    import sys

    from .config import load_config, paths
    from .fetch import fetch_all
    from .store import SeenStore

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s", stream=sys.stdout)
    conf = load_config()
    p = paths(conf)
    store = SeenStore(p["data"] / "seen.db")

    rescore = "--rescore" in sys.argv
    if rescore:
        # 离线模式：从库里读回已抓过的条目，只重算分数（不联网）
        raw = store.load_items()
        fresh = raw
        print(f"\n离线重算：从库里读回 {len(raw)} 条")
    else:
        before = store.stats()
        raw = fetch_all(conf)
        fresh = store.filter_new(raw)
        print(f"\n库里已有 {before['total']} 条；本次抓到 {len(raw)} 条，其中新的 {len(fresh)} 条")

    ranked = score_items(fresh, conf)
    store.save(ranked)

    th_mobile = float(conf["ranking"].get("mobile_threshold", 7.0))
    th_pc = float(conf["ranking"].get("pc_threshold", 5.0))

    print(f"\n===== 规则分 Top 15 =====")
    for rank, it in enumerate(ranked[:15], 1):
        parts = it.score_parts
        mark = "M" if it.score >= th_mobile else ("P" if it.score >= th_pc else " ")
        core_flag = "  " if parts.get("core") else "✗c"
        print(f"{rank:>2}. [{mark}] {it.score:5.2f}  "
              f"src={parts['source']:.2f} kw={parts['keyword']:.2f} "
              f"heat={parts['heat']:.2f} rec={parts['recency']:.2f} {core_flag} ({parts['track']})")
        print(f"    {it.title[:76]}")
        if parts["matched"]:
            print(f"    关键词: {', '.join(parts['matched'])}")
    print(f"\n手机阈值 {th_mobile} → {sum(1 for i in ranked if i.score >= th_mobile)} 条")
    print(f"电脑阈值 {th_pc} → {sum(1 for i in ranked if i.score >= th_pc)} 条")
    print(f"库总计: {store.stats()['total']} 条")
