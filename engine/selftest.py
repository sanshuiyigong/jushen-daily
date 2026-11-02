"""核心链路健康检查。

用途：每次改动之后跑一遍，确认**原有功能没有被新功能带坏**。

设计原则：只读，不写任何文件，不消耗 LLM 额度（除非加 --llm）。
它会依次检查：
    1. 配置能解析
    2. 数据库能打开
    3. 课程骨架完整、进度可读
    4. 打分能跑出结果
    5. 卡片能组装（用库里已有数据，不联网）
    6. 推送文案能生成（不发送）
    7. 各个源能不能连上（--net 才检查，会联网）
    8. LLM 能不能调通（--llm 才检查，会花钱）

用法：
    python -m engine.selftest            只查不联网的部分
    python -m engine.selftest --net      额外检查各数据源连通性
    python -m engine.selftest --llm      额外检查 LLM 调用
    python -m engine.selftest --net --llm   全查
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Checker:
    def __init__(self) -> None:
        self.results: list[tuple[str, bool, str]] = []

    def run(self, name: str, fn) -> bool:  # noqa: ANN001
        t0 = time.time()
        try:
            detail = fn() or ""
            ms = (time.time() - t0) * 1000
            self.results.append((name, True, f"{detail}  ({ms:.0f}ms)"))
            print(f"  ✔ {name:<26} {detail}  ({ms:.0f}ms)")
            return True
        except Exception as exc:  # noqa: BLE001
            ms = (time.time() - t0) * 1000
            self.results.append((name, False, f"{type(exc).__name__}: {exc}"))
            print(f"  ✘ {name:<26} {type(exc).__name__}: {exc}  ({ms:.0f}ms)")
            if "--trace" in sys.argv:
                traceback.print_exc()
            return False

    @property
    def failed(self) -> list[str]:
        return [n for n, ok, _ in self.results if not ok]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="engine.selftest", description="核心链路健康检查")
    parser.add_argument("--net", action="store_true", help="额外检查数据源连通性（联网）")
    parser.add_argument("--llm", action="store_true", help="额外检查 LLM 调用（花钱）")
    parser.add_argument("--trace", action="store_true", help="失败时打印完整堆栈")
    args = parser.parse_args(argv)

    from engine.card import concept_card, quiz_cards
    from engine.config import load_config, paths
    from engine.curriculum import Curriculum
    from engine.llm import LLMClient
    from engine.push import _compose
    from engine.rank import score_items
    from engine.store import SeenStore

    print()
    print("=" * 68)
    print("  核心链路健康检查")
    print("=" * 68)
    c = Checker()

    # ---- 1. 配置 ----
    state: dict = {}

    def check_config() -> str:
        cfg = load_config()
        state["cfg"] = cfg
        ranking = cfg.get("ranking") or {}
        core = ranking.get("core") or []
        assert ranking.get("mobile_threshold") is not None, "ranking.mobile_threshold 丢了"
        assert ranking.get("weights"), "ranking.weights 丢了"
        assert len(core) >= 10, f"核心词只有 {len(core)} 个，可能被写坏了"
        return (f"阈值 {ranking.get('mobile_threshold')}/{ranking.get('pc_threshold')}，"
                f"核心词 {len(core)} 个")

    c.run("配置解析", check_config)

    # ---- 2. 路径 ----
    def check_paths() -> str:
        p = paths(state["cfg"])
        state["p"] = p
        assert p["data"].exists(), "data 目录不存在"
        return f"{p['data']}"

    c.run("路径解析", check_paths)

    # ---- 3. 数据库 ----
    def check_db() -> str:
        store = SeenStore(state["p"]["data"] / "seen.db")
        state["store"] = store
        s = store.stats()
        assert s["total"] >= 0
        return f"{s['total']} 条记录"

    c.run("数据库", check_db)

    # ---- 4. 课程骨架 ----
    def check_curriculum() -> str:
        cur = Curriculum(state["p"]["curriculum"], state["p"]["data"] / "progress.json")
        state["cur"] = cur
        tracks = cur.tracks
        assert len(tracks) == 2, f"应该有 2 条轨道，实际 {len(tracks)}"
        total = sum(len(t.get("nodes") or []) for t in tracks.values())
        nxt = cur.next_overall()
        state["next"] = nxt
        return f"2 条轨道 / {total} 格 / 下一格 {nxt[1].get('title') if nxt else '已完成'}"

    c.run("课程骨架", check_curriculum)

    # ---- 5. 打分 ----
    def check_rank() -> str:
        items = state["store"].load_items(limit=200)
        if not items:
            return "库里没数据，跳过打分（不算失败）"
        ranked = score_items(items, state["cfg"])
        assert len(ranked) == len(items)
        assert all(0 <= it.score <= 10 for it in ranked[:20]), "分数超出 0~10"
        state["ranked"] = ranked
        return f"{len(ranked)} 条，第一名 {ranked[0].score:.2f}"

    c.run("规则打分", check_rank)

    # ---- 6. 卡片组装（模板路径，不花钱）----
    def check_cards() -> str:
        nxt = state.get("next")
        if not nxt:
            return "课程已学完，跳过"
        track_name, node = nxt
        label = (state["cur"].tracks.get(track_name) or {}).get("name", track_name)
        card = concept_card(node, label, "2000-01-01", None)
        quizzes = quiz_cards(node, "2000-01-01", 2, None)
        assert card["body"], "概念卡正文是空的"
        assert len(quizzes) >= 1, "没有生成题卡"
        state["sample_cards"] = [card, *quizzes]
        return f"概念 {len(card['body'])} 字 + {len(quizzes)} 道题"

    c.run("卡片组装（模板）", check_cards)

    # ---- 7. 推送文案（不发送）----
    def check_push_text() -> str:
        cards = state.get("sample_cards") or []
        ranked = state.get("ranked") or []
        day_data = {"day": "2000-01-01", "cards": list(cards)}
        if ranked:
            from engine.card import frontier_card
            day_data["cards"].append(frontier_card(ranked[0], "2000-01-01", None, "感知"))
        title, body = _compose(day_data, full=True)
        assert title and body, "推送文案是空的"
        size = len(body.encode("utf-8"))
        assert size < 4096, f"文案 {size} 字节，超过 ntfy 的 4096 上限"
        return f"{size} 字节（上限 4096）"

    c.run("推送文案生成", check_push_text)

    # ---- 8. 隔离检查：主流程不该导入插件 ----
    def check_isolation() -> str:
        banned = {"engine.assistant", "engine.patcher", "engine.dryrun", "server"}
        leaked = banned & set(sys.modules)
        assert not leaked, f"主流程被插件污染：{leaked}"
        return "run.py 未引入聊天/控制台模块"

    c.run("主流程隔离", check_isolation)

    # ---- 9. LLM（可选）----
    if args.llm:
        def check_llm() -> str:
            client = LLMClient(state["cfg"])
            assert client.available, "没有 key"
            reply = client.chat(
                [{"role": "user", "content": "只回复两个字：收到"}],
                temperature=0, max_tokens=20,
            )
            assert reply, "没有回复"
            return f"回复 {reply.strip()[:10]!r}"

        c.run("LLM 调用", check_llm)

    # ---- 10. 网络（可选）----
    if args.net:
        def check_fetch() -> str:
            from engine.fetch import fetch_all
            items = fetch_all(state["cfg"])
            assert items, "一条都没抓到"
            by_src: dict[str, int] = {}
            for it in items:
                by_src[it.source] = by_src.get(it.source, 0) + 1
            return " ".join(f"{k}:{v}" for k, v in sorted(by_src.items()))

        c.run("数据源抓取", check_fetch)

    # ---- 汇总 ----
    print("-" * 68)
    total = len(c.results)
    failed = c.failed
    if failed:
        print(f"  {total - len(failed)}/{total} 通过，失败：{', '.join(failed)}")
        print("=" * 68)
        return 1
    print(f"  全部 {total} 项通过 ✔")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
