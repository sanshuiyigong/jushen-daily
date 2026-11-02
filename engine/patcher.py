"""安全地修改配置文件。

三条原则，都是踩过坑之后定下来的：

1. **只做文本替换，不做 YAML 反序列化再序列化**
   PyYAML 一 dump，所有注释和空行就没了。而你这份 config.yaml 的价值
   有一半在注释里（每条参数为什么这么设）。

2. **替换目标必须在文件里恰好出现一次**
   出现 0 次说明模型看错了文件；出现 2 次以上说明这段文本有歧义，
   贸然替换会改错地方。两种情况都拒绝执行。

3. **只允许改白名单里的文件，且必须落在项目根目录内**
   聊天窗口背后是个 LLM，不能让它可以写任意路径。

每次成功修改都会自动 git commit，所以任何一次改动都能回滚。
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ALLOWED_FILES = {
    "config.yaml",
    "curriculum/perception.yaml",
    "curriculum/control.yaml",
}

MAX_PATCH_BYTES = 4000


class PatchError(Exception):
    """补丁不合法，拒绝执行。"""


def _resolve(root: Path, file: str) -> Path:
    rel = Path(str(file).strip())
    if rel.is_absolute() or ".." in rel.parts:
        raise PatchError(f"不允许的路径：{file}")

    normalized = str(rel).replace("\\", "/")
    if normalized not in ALLOWED_FILES:
        raise PatchError(
            f"不允许修改 {file}。只允许：{', '.join(sorted(ALLOWED_FILES))}"
        )

    path = (root / rel).resolve()
    if root.resolve() not in path.parents and path != root.resolve():
        raise PatchError(f"路径越界：{file}")
    if not path.exists():
        raise PatchError(f"文件不存在：{file}")
    return path


def read_file(root: Path, file: str) -> str:
    return _resolve(root, file).read_text(encoding="utf-8")


def validate_patch(root: Path, file: str, old: str, new: str) -> Path:
    """检查补丁能不能安全应用，返回目标路径。不写文件。"""
    if not old or not old.strip():
        raise PatchError("old 是空的，拒绝执行")
    if len(old.encode("utf-8")) > MAX_PATCH_BYTES or len(new.encode("utf-8")) > MAX_PATCH_BYTES:
        raise PatchError("补丁太大，怀疑是把整个文件塞进来了")

    path = _resolve(root, file)
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0:
        raise PatchError("在文件里找不到要替换的内容（可能缩进或换行不一致）")
    if count > 1:
        raise PatchError(f"要替换的内容出现了 {count} 次，不唯一，拒绝执行")

    # 改完之后仍然是合法 YAML 才允许写入
    candidate = text.replace(old, new, 1)
    try:
        yaml.safe_load(candidate)
    except yaml.YAMLError as exc:
        raise PatchError(f"改完会破坏 YAML 结构：{exc}") from exc

    return path


def apply_patch(root: Path, file: str, old: str, new: str, reason: str = "") -> dict[str, Any]:
    """应用一个补丁并自动 git commit。"""
    path = validate_patch(root, file, old, new)
    text = path.read_text(encoding="utf-8")
    updated = text.replace(old, new, 1)

    # 备份到 work 目录，双保险
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = Path(root) / "data" / "patches"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{path.stem}-{stamp}{path.suffix}"
    backup.write_text(text, encoding="utf-8")

    path.write_text(updated, encoding="utf-8")

    commit_msg = "chore: 调整配置" + (f"（{reason}）" if reason else "")
    committed = git_commit(root, commit_msg)

    return {
        "file": str(file).replace("\\", "/"),
        "reason": reason,
        "backup": str(backup.relative_to(Path(root))).replace("\\", "/"),
        "committed": committed,
    }


def git_commit(root: Path, message: str, paths: list[str] | None = None) -> bool:
    """提交改动。失败不算致命错误，只是没有自动回滚点。"""
    try:
        add_targets = paths or ["."]
        subprocess.run(
            ["git", "add", "--", *add_targets],
            cwd=str(root), check=True, capture_output=True, timeout=30,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root), capture_output=True, text=True, timeout=30,
        )
        if not status.stdout.strip():
            return False
        subprocess.run(
            ["git", "commit", "-q", "-m", message],
            cwd=str(root), check=True, capture_output=True, timeout=30,
        )
        return True
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return False


def config_summary(root: Path) -> str:
    """给聊天模型看的当前配置（只挑和调参有关的段落）。"""
    cfg = yaml.safe_load((Path(root) / "config.yaml").read_text(encoding="utf-8")) or {}
    ranking = cfg.get("ranking") or {}
    sources = cfg.get("sources") or {}
    general = cfg.get("general") or {}

    lines = ["## general"]
    for k in ("mobile_frontier_max", "quiz_per_day", "mobile_retention_days"):
        if k in general:
            lines.append(f"  {k}: {general[k]}")

    lines.append("## sources（weight 决定这个源的内容有多容易上榜）")
    for name, spec in sources.items():
        if isinstance(spec, dict):
            lines.append(
                f"  {name}: enabled={spec.get('enabled')} weight={spec.get('weight')}"
            )

    lines.append("## ranking 阈值")
    for k in ("mobile_threshold", "pc_threshold", "max_candidates"):
        if k in ranking:
            lines.append(f"  {k}: {ranking[k]}")

    weights = ranking.get("weights") or {}
    if weights:
        lines.append("## ranking.weights（四项加权，和必须为 1）")
        for k, v in weights.items():
            lines.append(f"  {k}: {v}")

    kws = ranking.get("keywords") or {}
    if kws:
        lines.append("## ranking.keywords（标题+摘要命中则累加）")
        lines.append("  " + "  ".join(f"{k}={v}" for k, v in kws.items()))

    return "\n".join(lines)


def curriculum_summary(root: Path) -> str:
    """课程骨架摘要。"""
    lines: list[str] = []
    for name in ("perception", "control"):
        path = Path(root) / "curriculum" / f"{name}.yaml"
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        nodes = sorted(data.get("nodes") or [], key=lambda n: n.get("order", 999))
        lines.append(f"## {data.get('name', name)}（{len(nodes)} 格）")
        for n in nodes:
            lines.append(f"  {n.get('order')}. {n.get('title')}  [{n.get('id')}]")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    root = Path(__file__).resolve().parent.parent
    print("=" * 60)
    print(config_summary(root))
    print()
    print(curriculum_summary(root))
    print("=" * 60)
    print("\n允许修改的文件：", ", ".join(sorted(ALLOWED_FILES)))
    sys.exit(0)
