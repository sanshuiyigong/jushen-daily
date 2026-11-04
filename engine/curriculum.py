"""课程骨架加载与进度管理。

骨架放在 curriculum/*.yaml，进度存在 data/progress.json。
「每天学哪一格」由这里决定，卡片生成（card.py）只是把它展开成文案。

进度只记「学完的日期」，不记顺序——顺序由 yaml 里的 order 决定。
这样以后调整课程顺序，历史进度不会乱。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .clock import stamp as stamp_bj
from .clock import today as today_bj

TRACK_FILES = ("perception", "control")


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(str(tmp), str(path))


def _days_between(start: str, end: str) -> int:
    """两个 YYYY-MM-DD 之间差几天。解析失败返回 0。"""
    try:
        a = datetime.strptime(start[:10], "%Y-%m-%d")
        b = datetime.strptime(end[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return 0
    return (b - a).days


class Curriculum:
    def __init__(self, curriculum_dir: Path, progress_path: Path):
        self.dir = Path(curriculum_dir)
        self.progress_path = Path(progress_path)
        self.tracks: dict[str, dict[str, Any]] = {}
        self._load_tracks()
        self._done, self._started = self._load_progress()

    # ------------------------------------------------------------ 加载
    def _load_tracks(self) -> None:
        for name in TRACK_FILES:
            path = self.dir / f"{name}.yaml"
            if not path.exists():
                continue
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            nodes = sorted(data.get("nodes") or [], key=lambda n: n.get("order", 999))
            data["nodes"] = nodes
            self.tracks[name] = data

    def _load_progress(self) -> tuple[dict[str, str], dict[str, str]]:
        if not self.progress_path.exists():
            return {}, {}
        try:
            data = json.loads(self.progress_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}, {}
        done = data.get("done")
        started = data.get("started")
        return (
            dict(done) if isinstance(done, dict) else {},
            dict(started) if isinstance(started, dict) else {},
        )

    def save_progress(self) -> None:
        self.progress_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": stamp_bj(),
            "done": self._done,
            "started": self._started,
        }
        _atomic_write(self.progress_path, json.dumps(payload, ensure_ascii=False, indent=2))

    # ------------------------------------------------------------ 查询
    def node(self, node_id: str) -> dict[str, Any] | None:
        for track in self.tracks.values():
            for n in track["nodes"]:
                if n.get("id") == node_id:
                    return n
        return None

    def track_of(self, node_id: str) -> str | None:
        for name, track in self.tracks.items():
            if any(n.get("id") == node_id for n in track["nodes"]):
                return name
        return None

    def is_done(self, node_id: str) -> bool:
        return node_id in self._done

    def done_count(self, track_name: str) -> int:
        track = self.tracks.get(track_name) or {}
        return sum(1 for n in track.get("nodes", []) if n.get("id") in self._done)

    def current(self, track_name: str) -> dict[str, Any] | None:
        """该轨道里第一个「前置都学完、自己没学完」的节点。"""
        track = self.tracks.get(track_name) or {}
        for node in track.get("nodes", []):
            nid = node.get("id")
            if not nid or nid in self._done:
                continue
            prereq = node.get("prereq") or []
            if all(p in self._done for p in prereq):
                return node
        return None

    def next_overall(self) -> tuple[str, dict[str, Any]] | None:
        """两条线里挑「完成比例更低」的那条，取它的下一格。"""
        best: tuple[str, dict[str, Any]] | None = None
        best_ratio = 2.0
        for name, track in self.tracks.items():
            total = len(track.get("nodes") or [])
            if total == 0:
                continue
            ratio = self.done_count(name) / total
            node = self.current(name)
            if node and ratio < best_ratio:
                best_ratio = ratio
                best = (name, node)
        return best

    def status(self) -> list[dict[str, Any]]:
        rows = []
        for name, track in self.tracks.items():
            total = len(track.get("nodes") or [])
            node = self.current(name)
            rows.append(
                {
                    "track": name,
                    "label": track.get("name", name),
                    "done": self.done_count(name),
                    "total": total,
                    "current": (node or {}).get("title"),
                    "current_id": (node or {}).get("id"),
                }
            )
        return rows

    # ------------------------------------------------------------ 变更
    def mark_done(self, node_id: str, day: str | None = None) -> bool:
        if not node_id or node_id in self._done:
            return False
        self._done[node_id] = day or today_bj()
        self.save_progress()
        return True

    def start(self, node_id: str, day: str | None = None) -> None:
        """记录某个节点第一次开始学的日期（只记一次，不覆盖）。"""
        if not node_id or node_id in self._started:
            return
        self._started[node_id] = day or today_bj()
        self.save_progress()

    def stage_of(self, node: dict[str, Any], day: str | None = None) -> tuple[int, int]:
        """这个节点今天是第几天的学习（1-based），以及总共几天。

        用来让「同一个节点连续几天」每天换个角度，而不是复读同一篇。
        """
        today = day or today_bj()
        try:
            total = max(1, int(node.get("estimated_days") or 1))
        except (TypeError, ValueError):
            total = 1
        started = self._started.get(node.get("id"))
        if not started:
            return 1, total
        idx = _days_between(started, today) + 1
        return max(1, min(idx, total)), total

    def auto_advance(self, day: str | None = None) -> list[str]:
        """按 estimated_days 把「学够天数」的节点标记为完成。

        这是 v1 的简化：手机端的答题数据还没回传，所以进度只能按时长推进。
        等手机端把自评结果写回来之后，这里应该改成「答对才推进」。
        """
        today = day or today_bj()
        advanced: list[str] = []
        for name in list(self.tracks):
            node = self.current(name)
            if not node:
                continue
            node_id = node.get("id")
            started = self._started.get(node_id)
            if not started:
                continue
            try:
                est = int(node.get("estimated_days") or 1)
            except (TypeError, ValueError):
                est = 1
            if _days_between(started, today) >= est:
                self._done[node_id] = today
                advanced.append(node_id)
        if advanced:
            self.save_progress()
        return advanced

    def reset(self) -> None:
        self._done = {}
        self._started = {}
        self.save_progress()


if __name__ == "__main__":
    import logging
    import sys

    from .config import load_config, paths

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s", stream=sys.stdout)
    cfg = load_config()
    p = paths(cfg)
    cur = Curriculum(p["curriculum"], p["data"] / "progress.json")

    print("\n===== 课程进度 =====")
    for row in cur.status():
        print(f"  {row['label']:<12} {row['done']}/{row['total']}  下一格: {row['current']}")

    nxt = cur.next_overall()
    if nxt:
        name, node = nxt
        print(f"\n===== 今日该学：{name} · {node['title']} =====")
        print(f"  目标: {node.get('goal')}")
        print(f"  预计: {node.get('estimated_days')} 天")
        print(f"  前置: {node.get('prereq') or '无'}")
        print("  检验点:")
        for cp in node.get("checkpoints") or []:
            print(f"    · {cp}")
        print("  原始材料:")
        for rd in node.get("reading") or []:
            print(f"    · {rd.get('title')}")
