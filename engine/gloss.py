"""把英文标题翻成中文，带本地缓存。

为什么要缓存：
    论文标题基本都是英文。控制台上一整面色块全是英文，看不懂就等于没用。
    但每次打开页面都去调 LLM 翻译又太浪费——同一条内容这辈子只需要翻一次。
    翻完写进 data/gloss.json，以后直接读文件，零成本零延迟。

翻译策略：
    一次请求翻一批（默认 15 条），带上摘要的前 120 字当上下文，
    否则光看标题容易把 "world model" 翻成 "世界模型" 却不知道是哪个领域的世界模型。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .llm import LLMClient

LOG = logging.getLogger("gloss")

CACHE_NAME = "gloss.json"

SYS = (
    "你是学术翻译。把论文或项目的标题翻成准确、通顺的中文。"
    "要求：不要直译，不要生造词，不要加任何解释或标点之外的修饰；"
    "专有名词（模型名、数据集名、公司名）保留英文；"
    "长度尽量和原标题相当。"
)


def cache_path(data_dir: Path) -> Path:
    return Path(data_dir) / CACHE_NAME


def load_cache(data_dir: Path) -> dict[str, str]:
    path = cache_path(data_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(data_dir: Path, cache: dict[str, str]) -> None:
    path = cache_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _ask_batch(batch: list[dict[str, str]], llm: LLMClient) -> dict[str, str]:
    """翻一批，返回 {key: 中文}。"""
    lines: list[str] = []
    for idx, item in enumerate(batch):
        lines.append(f"[{idx}] {item['title']}")
        if item.get("summary"):
            lines.append(f"    摘要：{item['summary'][:120]}")
    listing = "\n".join(lines)

    user = f"""把下面这 {len(batch)} 条标题翻成中文。

{listing}

输出 JSON：
{{"translations": [{{"i": 编号, "zh": "中文标题"}}]}}

要求：编号必须和上面一一对应；只翻译标题本身；专有名词保留英文。"""

    obj = llm.chat_json(SYS, user, temperature=0.2, max_tokens=1600)
    if not obj:
        return {}

    out: dict[str, str] = {}
    for row in obj.get("translations") or []:
        if not isinstance(row, dict):
            continue
        try:
            i = int(row.get("i", -1))
        except (TypeError, ValueError):
            continue
        zh = str(row.get("zh") or "").strip()
        if 0 <= i < len(batch) and zh:
            out[batch[i]["key"]] = zh
    return out


def translate(
    entries: list[dict[str, Any]],
    llm: LLMClient | None,
    data_dir: Path,
    *,
    limit: int = 40,
    batch_size: int = 15,
) -> dict[str, str]:
    """返回 {key: 中文标题}。没 key 或调用失败时，缺的那部分就不返回，调用方回退英文。"""
    cache = load_cache(data_dir)

    if not llm or not llm.available:
        return cache

    todo: list[dict[str, str]] = []
    for e in entries[:limit]:
        key = str(e.get("key") or "")
        if not key or key in cache:
            continue
        todo.append(
            {
                "key": key,
                "title": str(e.get("title") or ""),
                "summary": str(e.get("summary") or ""),
            }
        )

    if not todo:
        return cache

    LOG.info("需要翻译 %d 条标题", len(todo))
    for start in range(0, len(todo), batch_size):
        chunk = todo[start : start + batch_size]
        try:
            got = _ask_batch(chunk, llm)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("翻译失败（跳过这批）：%s", exc)
            continue
        if got:
            cache.update(got)
            save_cache(data_dir, cache)
            LOG.info("  本批翻译 %d/%d 条", len(got), len(chunk))

    return cache


if __name__ == "__main__":
    import sys

    from .config import load_config, paths
    from .dryrun import pool
    from .store import SeenStore

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s", stream=sys.stdout)
    cfg = load_config()
    p = paths(cfg)
    store = SeenStore(p["data"] / "seen.db")
    items = store.load_items()
    rows = pool(items, cfg, top=20)

    client = LLMClient(cfg)
    entries = [{"key": r["key"], "title": r["title"], "summary": r.get("summary", "")} for r in rows]
    table = translate(entries, client, p["data"])

    print()
    for r in rows[:20]:
        zh = table.get(r["key"], "（未翻译）")
        print(f"  {r['score']:5.2f}  {zh}")
        print(f"         {r['title'][:70]}")
