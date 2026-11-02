"""去重库 + 本地缓存（SQLite）。

一个表干三件事：
1. 去重 —— 已经推过的东西不再出现（这是全系统长期可用的命门）
2. 缓存 —— 存完整 payload，断网时可以离线调打分器
3. 状态 —— 记录哪些已经推到手机
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import fields
from pathlib import Path
from typing import Iterable, Iterator

from .models import Item, utc_now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    key         TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    score       REAL DEFAULT 0,
    pushed      INTEGER DEFAULT 0,
    payload     TEXT
);
CREATE INDEX IF NOT EXISTS idx_seen_first  ON seen(first_seen);
CREATE INDEX IF NOT EXISTS idx_seen_pushed ON seen(pushed);
CREATE INDEX IF NOT EXISTS idx_seen_score  ON seen(score);
"""

_ITEM_FIELDS = {f.name for f in fields(Item)}


class SeenStore:
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as con:
            con.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    # ---------------------------------------------------------- 查询
    def known_keys(self) -> set[str]:
        with self._conn() as con:
            return {row["key"] for row in con.execute("SELECT key FROM seen")}

    def filter_new(self, items: Iterable[Item]) -> list[Item]:
        """只返回库里没有的（也就是今天真正的新东西）。"""
        known = self.known_keys()
        return [it for it in items if it.key not in known]

    def stats(self) -> dict[str, int]:
        with self._conn() as con:
            total = con.execute("SELECT COUNT(*) FROM seen").fetchone()[0]
            pushed = con.execute("SELECT COUNT(*) FROM seen WHERE pushed=1").fetchone()[0]
        return {"total": total, "pushed": pushed}

    # ---------------------------------------------------------- 写入
    def save(self, items: Iterable[Item]) -> int:
        """插入新条目；已有的只更新 last_seen / score，保留 first_seen。"""
        now = utc_now_iso()
        rows = []
        for it in items:
            payload = json.dumps(
                {k: v for k, v in it.to_dict().items()}, ensure_ascii=False
            )
            rows.append(
                (
                    it.key,
                    it.source,
                    it.title,
                    it.url,
                    now,
                    now,
                    float(it.score),
                    payload,
                )
            )
        if not rows:
            return 0
        with self._conn() as con:
            con.executemany(
                """
                INSERT INTO seen (key, source, title, url, first_seen, last_seen, score, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    last_seen = excluded.last_seen,
                    score     = excluded.score,
                    source    = excluded.source,
                    payload   = excluded.payload
                """,
                rows,
            )
        return len(rows)

    def mark_pushed(self, keys: Iterable[str]) -> int:
        keys = list(keys)
        if not keys:
            return 0
        with self._conn() as con:
            con.executemany("UPDATE seen SET pushed=1 WHERE key=?", [(k,) for k in keys])
        return len(keys)

    # ---------------------------------------------------------- 读回
    def load_items(self, *, days: int | None = None, min_score: float | None = None,
                   limit: int | None = None) -> list[Item]:
        """把库里的条目反序列化成 Item，用于离线调参 / 试跑对比。"""
        clauses: list[str] = []
        params: list[object] = []
        if days is not None:
            clauses.append("first_seen >= datetime('now', ?)")
            params.append(f"-{int(days)} days")
        if min_score is not None:
            clauses.append("score >= ?")
            params.append(float(min_score))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = "ORDER BY first_seen DESC"
        tail = f"LIMIT {int(limit)}" if limit else ""
        sql = f"SELECT payload FROM seen {where} {order} {tail}"

        out: list[Item] = []
        with self._conn() as con:
            for row in con.execute(sql, params):
                if not row["payload"]:
                    continue
                try:
                    data = json.loads(row["payload"])
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, dict):
                    continue
                out.append(Item(**{k: v for k, v in data.items() if k in _ITEM_FIELDS}))
        return out
