"""统一条目模型 + 去重键归一化。

去重键的设计是全系统的地基：
- arXiv 用 arXiv id（HF 的 paper.id 也是 arXiv id，所以两个源会天然合并）
- GitHub 用 full_name
- HN 用 objectID
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_ARXIV_ID = re.compile(r"(\d{4}\.\d{4,5})")
_TRACKING_KEYS = {"ref", "from", "spm", "share_token", "source", "fbclid", "gclid"}
_TRACKING_PREFIXES = ("utm_",)


def arxiv_id_from(*candidates: str | None) -> str | None:
    """从任意字符串里抠出 arXiv id（去掉版本号）。"""
    for cand in candidates:
        if not cand:
            continue
        match = _ARXIV_ID.search(str(cand))
        if match:
            return match.group(1)
    return None


def norm_url(url: str) -> str:
    """去掉追踪参数、锚点、尾斜杠，域名小写。"""
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in _TRACKING_KEYS
        and not any(k.lower().startswith(p) for p in _TRACKING_PREFIXES)
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, urlencode(query), ""))


def make_key(source: str, url: str, title: str = "", arxiv_id: str | None = None) -> str:
    """生成稳定、跨源一致的去重键。"""
    if arxiv_id:
        return f"arxiv:{arxiv_id}"
    if source.startswith("gh:") or source == "github":
        return f"gh:{title.strip().lower()}"
    if source == "hn":
        return f"hn:{url}"
    normalized = norm_url(url)
    if normalized and normalized != "/":
        return f"url:{normalized}"
    digest = hashlib.sha1(title.strip().lower().encode("utf-8")).hexdigest()[:12]
    return f"txt:{digest}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_loose(value: str | None) -> datetime | None:
    """尽量解析各种 ISO 变体，失败返回 None。"""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    if "." in text:
        head, _, tail = text.partition(".")
        frac = re.match(r"(\d+)", tail)
        rest = tail[frac.end():] if frac else ""
        text = f"{head}.{frac.group(1)[:6]}{rest}" if frac else head + rest
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass
class Item:
    """一条候选内容。所有源都必须产出这个结构。"""

    key: str
    source: str
    title: str
    url: str
    summary: str = ""
    published: str | None = None
    heat: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    # 排序阶段填充
    score: float = 0.0
    score_parts: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    @property
    def age_hours(self) -> float:
        dt = parse_iso_loose(self.published)
        if not dt:
            return 24 * 30.0
        delta = datetime.now(timezone.utc) - dt
        return max(delta.total_seconds() / 3600.0, 0.0)
