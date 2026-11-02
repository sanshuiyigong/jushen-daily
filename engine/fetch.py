"""数据源适配器：把各家 API 的返回统一成 Item。

设计要点
- 所有源都产出 Item，去重键由 models.make_key 统一生成
- HF 的 paper.id 就是 arXiv id，所以 HF 和 arXiv 会自动合并成一条
- 单个源失败不影响其他源（网络抖动是常态）
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import requests
from xml.etree import ElementTree as ET

from .config import load_config
from .models import Item, arxiv_id_from, make_key, parse_iso_loose
from .net import make_session

LOG = logging.getLogger("fetch")

# 按源分别选路：
#   hf-mirror 是国内镜像，直连最快，绕道国外反而慢
#   arXiv / GitHub / HN 都在国外，实测 arXiv 直连 18.9 秒、走代理 2.9 秒
# 云端（GitHub Actions）探测不到本地代理，两个会话都退化成直连，行为一致。
_SESSION_DIRECT = make_session(proxy="")
_SESSION_AUTO = make_session()

UA = {
    "User-Agent": "jushen-daily/0.1 (personal research digest)",
    "Accept": "application/json, application/atom+xml, text/xml, */*",
}
ARXIV_NS = {"a": "http://www.w3.org/2005/Atom"}
_WS = re.compile(r"\s+")


def _clean(text: Any) -> str:
    return _WS.sub(" ", str(text or "")).strip()


def _get(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    retries: int = 2,
    backoff: float = 2.0,
    session: requests.Session | None = None,
) -> requests.Response:
    merged = dict(UA)
    if headers:
        merged.update(headers)
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = (session or _SESSION_AUTO).get(url, params=params, headers=merged, timeout=timeout)
            # 401/403 是限流或鉴权问题，重试只会更糟，直接放弃
            if resp.status_code in (401, 403):
                raise RuntimeError(f"HTTP {resp.status_code}（限流/鉴权，不重试）")
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                raise requests.HTTPError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            return resp
        except RuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < retries:
                wait = backoff * (attempt + 1)
                LOG.warning("GET %s 失败（%s），%.0fs 后重试", url, exc, wait)
                time.sleep(wait)
    raise RuntimeError(f"GET {url} 最终失败: {last}") from last


# ---------------------------------------------------------------- arXiv
def fetch_arxiv(category: str, max_results: int = 40, name: str = "arxiv_ro") -> list[Item]:
    resp = _get(
        "https://export.arxiv.org/api/query",
        params={
            "search_query": f"cat:{category}",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": int(max_results),
        },
    )
    root = ET.fromstring(resp.content)
    items: list[Item] = []
    for entry in root.findall("a:entry", ARXIV_NS):
        raw_id = _clean(entry.findtext("a:id", default="", namespaces=ARXIV_NS))
        aid = arxiv_id_from(raw_id)
        title = _clean(entry.findtext("a:title", default="", namespaces=ARXIV_NS))
        if not aid or not title:
            continue
        pdf = None
        for link in entry.findall("a:link", ARXIV_NS):
            if link.get("type") == "application/pdf":
                pdf = link.get("href")
        items.append(
            Item(
                key=make_key("arxiv", "", title, arxiv_id=aid),
                source=name,
                title=title,
                url=f"https://arxiv.org/abs/{aid}",
                summary=_clean(entry.findtext("a:summary", default="", namespaces=ARXIV_NS)),
                published=_clean(entry.findtext("a:published", default="", namespaces=ARXIV_NS)),
                extra={
                    "arxiv_id": aid,
                    "pdf": pdf or f"https://arxiv.org/pdf/{aid}",
                    "authors": [
                        a.text for a in entry.findall("a:author/a:name", ARXIV_NS) if a.text
                    ][:8],
                    "category": category,
                },
            )
        )
    return items


# ------------------------------------------------------------- HF Papers
def fetch_hf_papers(base_url: str, limit: int = 30) -> list[Item]:
    try:
        resp = _get(
            f"{base_url.rstrip('/')}/api/daily_papers",
            params={"limit": int(limit)},
            session=_SESSION_DIRECT,   # 国内镜像，直连最快
        )
    except Exception as exc:  # noqa: BLE001
        # 直连偶尔会被重置（实测过瞬时抖动）。退一步走代理，总比整源丢掉好。
        LOG.warning("hf 直连失败（%s），改走代理重试", exc)
        resp = _get(
            f"{base_url.rstrip('/')}/api/daily_papers",
            params={"limit": int(limit)},
            session=_SESSION_AUTO,
        )
    data = resp.json()
    if not isinstance(data, list):
        LOG.warning("HF 返回不是列表，跳过")
        return []
    items: list[Item] = []
    for row in data:
        paper = row.get("paper") or {}
        pid = _clean(paper.get("id"))
        title = _clean(paper.get("title") or row.get("title"))
        if not title:
            continue
        aid = arxiv_id_from(pid, title)
        summary = _clean(paper.get("ai_summary") or paper.get("summary") or row.get("summary"))
        url = f"https://arxiv.org/abs/{aid}" if aid else f"https://huggingface.co/papers/{pid}"
        upvotes = float(paper.get("upvotes") or 0)
        items.append(
            Item(
                key=make_key("hf", url, title, arxiv_id=aid),
                source="hf_papers",
                title=title,
                url=url,
                summary=summary,
                published=paper.get("publishedAt") or row.get("publishedAt"),
                heat=upvotes,
                extra={
                    "arxiv_id": aid,
                    "pdf": paper.get("pdf") or (f"https://arxiv.org/pdf/{aid}" if aid else None),
                    "github": paper.get("githubRepo"),
                    "project": paper.get("projectPage"),
                    "upvotes": upvotes,
                    "keywords": paper.get("ai_keywords") or [],
                    "hf_discussion": paper.get("discussionId"),
                },
            )
        )
    return items


# --------------------------------------------------------------- GitHub
def fetch_github(
    topics: Iterable[str],
    min_stars: int = 10,
    days: int = 21,
    token: str = "",
    name: str = "github",
) -> list[Item]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    items: list[Item] = []
    for topic in topics:
        query = f"topic:{topic} created:>{since} stars:>={int(min_stars)}"
        try:
            resp = _get(
                "https://api.github.com/search/repositories",
                params={"q": query, "sort": "stars", "order": "desc", "per_page": 10},
                headers=headers,
                retries=1,
            )
        except Exception as exc:  # noqa: BLE001
            LOG.warning("GitHub topic=%s 失败：%s", topic, exc)
            continue
        for repo in resp.json().get("items", []):
            full_name = _clean(repo.get("full_name"))
            if not full_name:
                continue
            items.append(
                Item(
                    key=f"gh:{full_name.lower()}",
                    source=name,
                    title=full_name,
                    url=repo.get("html_url") or f"https://github.com/{full_name}",
                    summary=_clean(repo.get("description")),
                    published=repo.get("pushed_at") or repo.get("created_at"),
                    heat=float(repo.get("stargazers_count") or 0),
                    extra={
                        "topic": topic,
                        "stars": repo.get("stargazers_count"),
                        "language": repo.get("language"),
                        "topics": repo.get("topics") or [],
                        "created_at": repo.get("created_at"),
                        "forks": repo.get("forks_count"),
                    },
                )
            )
        time.sleep(6.0)  # GitHub 搜索接口未认证限流 10 次/分钟，必须拉开间隔
    return items


# ------------------------------------------------------------------- HN
def _hit_any(title: str, keywords: Iterable[str]) -> bool:
    low = title.lower()
    for kw in keywords:
        word = kw.lower().strip()
        if not word:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", low):
            return True
    return False


def fetch_hn(
    keywords: Iterable[str],
    min_points: int = 40,
    days: int = 3,
    scan: int = 300,
) -> list[Item]:
    """一次请求拉近 N 天所有高分帖，再用关键词白名单过滤标题。

    比按关键词查询靠谱得多：Algolia 的 query 参数是全字段模糊匹配，
    查 'VLA' 会返回 'Nurses Sound Alarm' 这种完全不相关的结果。
    """
    keywords = list(keywords)
    since_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    try:
        resp = _get(
            "https://hn.algolia.com/api/v1/search_by_date",
            params={
                "tags": "story",
                "numericFilters": f"points>{int(min_points)},created_at_i>{since_ts}",
                "hitsPerPage": int(scan),
            },
            retries=2,
        )
    except Exception as exc:  # noqa: BLE001
        LOG.warning("HN 抓取失败：%s", exc)
        return []

    hits = resp.json().get("hits", [])
    items: list[Item] = []
    for hit in hits:
        oid = _clean(hit.get("objectID"))
        title = _clean(hit.get("title") or hit.get("story_title"))
        if not oid or not title:
            continue
        if not _hit_any(title, keywords):
            continue
        items.append(
            Item(
                key=f"hn:{oid}",
                source="hn",
                title=title,
                url=hit.get("url") or f"https://news.ycombinator.com/item?id={oid}",
                summary=_clean(hit.get("story_text"))[:400],
                published=hit.get("created_at"),
                heat=float(hit.get("points") or 0),
                extra={
                    "hn_id": oid,
                    "comments": hit.get("num_comments"),
                    "hn_url": f"https://news.ycombinator.com/item?id={oid}",
                },
            )
        )
    LOG.info("HN 扫描 %d 条高分帖，命中关键词 %d 条", len(hits), len(items))
    return items


# ---------------------------------------------------------------- 合并
def source_weight_of(source: str, weights: dict[str, float]) -> float:
    """source 形如 'arxiv:cs.RO' / 'hf_papers' / 'hn:robot'，取最长前缀匹配。"""
    best, best_len = 0.0, -1
    for name, weight in weights.items():
        if source == name or source.startswith(name + ":"):
            if len(name) > best_len:
                best, best_len = float(weight), len(name)
    return best


def merge_items(items: list[Item], weights: dict[str, float]) -> list[Item]:
    """按 key 合并；同一篇论文被多个源抓到时，保留信息更全的那份。"""
    merged: dict[str, Item] = {}
    for item in items:
        existing = merged.get(item.key)
        if existing is None:
            merged[item.key] = item
            continue
        winner, loser = (
            (item, existing)
            if source_weight_of(item.source, weights) > source_weight_of(existing.source, weights)
            else (existing, item)
        )
        # 补齐对方有、自己缺的字段
        if not winner.summary and loser.summary:
            winner.summary = loser.summary
        if len(loser.summary) > len(winner.summary) * 1.5 and not winner.extra.get("keywords"):
            winner.summary = loser.summary
        if not winner.published and loser.published:
            winner.published = loser.published
        winner.heat = max(winner.heat, loser.heat)
        for k, v in loser.extra.items():
            if v and not winner.extra.get(k):
                winner.extra[k] = v
        merged[item.key] = winner
    return list(merged.values())


def fetch_all(cfg: dict[str, Any], only: Iterable[str] | None = None) -> list[Item]:
    """按配置抓取所有启用的源。单个源异常不会中断整体。"""
    sources = cfg.get("sources", {})
    weights = {name: float(spec.get("weight", 0.5)) for name, spec in sources.items()}
    wanted = set(only) if only else None
    collected: list[Item] = []

    def enabled(name: str) -> bool:
        spec = sources.get(name) or {}
        if not spec.get("enabled", False):
            return False
        return wanted is None or name in wanted

    def run(name: str, fn) -> None:  # noqa: ANN001
        started = time.time()
        try:
            got = fn()
        except Exception as exc:  # noqa: BLE001
            LOG.error("源 %s 抓取失败：%s", name, exc)
            return
        LOG.info("源 %-12s 抓到 %3d 条（%.1fs）", name, len(got), time.time() - started)
        collected.extend(got)

    if enabled("arxiv_ro"):
        run("arxiv_ro", lambda s=sources["arxiv_ro"]: fetch_arxiv(
            s.get("category", "cs.RO"), s.get("max_results", 40), "arxiv_ro"))
        time.sleep(3)  # arXiv 要求请求间隔
    if enabled("arxiv_cv"):
        run("arxiv_cv", lambda s=sources["arxiv_cv"]: fetch_arxiv(
            s.get("category", "cs.CV"), s.get("max_results", 25), "arxiv_cv"))
    if enabled("hf_papers"):
        run("hf_papers", lambda s=sources["hf_papers"]: fetch_hf_papers(
            s.get("base_url", "https://hf-mirror.com"), s.get("limit", 30)))
    if enabled("github"):
        run("github", lambda s=sources["github"]: fetch_github(
            s.get("topics", []), s.get("min_stars", 10),
            s.get("days", 21), s.get("token", ""), "github"))
    if enabled("hn"):
        run("hn", lambda s=sources["hn"]: fetch_hn(
            s.get("keywords", []), s.get("min_points", 40),
            s.get("days", 3), s.get("scan", 300)))

    before = len(collected)
    merged = merge_items(collected, weights)
    LOG.info("合并去重：%d → %d 条", before, len(merged))
    # 顺手丢掉太老的
    fresh = [i for i in merged if i.age_hours <= 24 * 45]
    if len(fresh) != len(merged):
        LOG.info("丢弃超过 45 天的 %d 条", len(merged) - len(fresh))
    return fresh


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)-7s %(message)s",
        stream=sys.stdout,
    )
    conf = load_config()
    got = fetch_all(conf)
    groups: dict[str, list[Item]] = {}
    for it in got:
        groups.setdefault(it.source.split(":")[0], []).append(it)
    print("\n===== 按源统计 =====")
    for name, bucket in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        print(f"  {name:<14} {len(bucket):>3} 条")
    print(f"  {'合计':<14} {len(got):>3} 条")

    print("\n===== 各源抽样 3 条（检验相关性）=====")
    for name, bucket in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        print(f"\n-- {name} --")
        for it in bucket[:3]:
            print(f"  · {it.title[:78]}")
            print(f"    {it.url}")
            if it.summary:
                print(f"    {it.summary[:110]}…")
