"""统一用北京时间判断「今天是哪天」。

为什么必须有这个模块：
    GitHub Actions 的机器跑在 UTC。定时任务设在北京早 7:30，
    对应 UTC 是**前一天的** 23:30。如果代码用 datetime.now() 取日期，
    在云端会拿到「昨天」，后果是：

      · 今天生成的内容被记到昨天名下
      · push_state 认为昨天已经推过 → 直接跳过推送 → 早上收不到任何东西
      · 去重库、课程进度、归档全部错位一天

    这类 bug 在本地跑永远看不出来（本地就是北京时间），
    只在云端定时那一跑才暴露。所以所有「今天是哪天」的判断都必须走这里。

用法：
    from engine.clock import today, now, stamp
    day = today()            # "2026-11-04"
    ts  = stamp()            # "2026-11-04T11:05:07+08:00"
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# 中国没有夏令时，固定 +8 即可
BEIJING = timezone(timedelta(hours=8), "Asia/Shanghai")


def now() -> datetime:
    """当前的北京时间（带时区）。"""
    return datetime.now(BEIJING)


def today() -> str:
    """北京时间的今天，格式 2026-11-04。"""
    return now().strftime("%Y-%m-%d")


def stamp() -> str:
    """带时区的 ISO 时间戳，用于记录写入时刻。"""
    return now().isoformat(timespec="seconds")
