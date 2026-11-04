"""从归档重建 Pages 站点，不调 LLM、不抓网络、不推送。

为什么需要这个：
    run.py 在本地跑完会 ①推送到手机 ②写入 data/archive ③提交到 git。
    但网页（GitHub Pages）只有云端部署才会更新，于是出现错位：
    手机已经收到今天的卡片，点进链接却还是旧页面。

    这个脚本让云端只需要「把归档变成网页」——几秒钟、零成本，
    由 .github/workflows/sync-site.yml 在归档变化时自动调用。
    这样本地和云端两条路走出来的结果在网页上是一致的。

用法（云端）：
    python tools/build_site.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.cardset import write_recent  # noqa: E402


def main() -> int:
    out = ROOT / "output"
    out.mkdir(parents=True, exist_ok=True)

    # 只从归档重建最近 7 天；当天如果本地有 day 文件会自动优先用那份
    path = write_recent(out, keep_days=7, data_dir=ROOT / "data")
    print(f"recent7.json -> {path}")

    public = ROOT / "public"
    shutil.rmtree(public, ignore_errors=True)
    shutil.copytree(ROOT / "web", public / "web")
    (public / "output").mkdir(parents=True, exist_ok=True)
    shutil.copy(out / "recent7.json", public / "output" / "recent7.json")

    # 根目录也放一份入口，这样 .../jushen-daily/ 直接能打开
    shutil.copy(ROOT / "web" / "index.html", public / "index.html")
    shutil.copy(ROOT / "web" / "favicon.ico", public / "favicon.ico")

    files = [f for f in public.rglob("*") if f.is_file()]
    print(f"站点文件 {len(files)} 个：")
    for f in sorted(files)[:40]:
        print("  ", f.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
