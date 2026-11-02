"""本地服务：手机页面 + 电脑端控制台 + 几个 API。

路由：
    GET  /                 → 手机答题页（web/index.html）
    GET  /admin            → 电脑端控制台（web/admin.html）
    GET  /web/*, /output/* → 静态文件
    POST /api/chat         → 聊天调参（返回补丁提议，不写文件）
    POST /api/apply        → 应用一个补丁（用户点「应用」后才走到这）
    POST /api/dryrun       → 试跑对比
    POST /api/status       → 当前状态（git、库、卡片数）

它只在局域网里活，不做鉴权。用完关掉即可。
"""

from __future__ import annotations

import http.server
import json
import logging
import socket
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.assistant import apply as apply_patch_call  # noqa: E402
from engine.assistant import ask as ask_call  # noqa: E402
from engine.config import load_config  # noqa: E402
from engine.dryrun import compare, pool, render as render_dryrun  # noqa: E402
from engine.llm import LLMClient  # noqa: E402
from engine.store import SeenStore  # noqa: E402

START_PORT = 8000
MAX_TRIES = 10

LOG = logging.getLogger("server")


def lan_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
        super().__init__(*args, directory=str(ROOT), **kwargs)

    # ------------------------------------------------------------ 工具
    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            return {}
        if length <= 0 or length > 5_000_000:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    # ------------------------------------------------------------ GET
    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._redirect("/web/index.html")
            return
        if self.path in ("/admin", "/admin/", "/admin.html"):
            self._redirect("/web/admin.html")
            return
        super().do_GET()

    # ----------------------------------------------------------- POST
    def do_POST(self) -> None:  # noqa: N802
        route = self.path.split("?")[0].rstrip("/")
        try:
            if route == "/api/chat":
                self._handle_chat()
            elif route == "/api/apply":
                self._handle_apply()
            elif route == "/api/dryrun":
                self._handle_dryrun()
            elif route == "/api/status":
                self._handle_status()
            elif route == "/api/pool":
                self._handle_pool()
            else:
                self._send_json({"ok": False, "error": f"未知接口：{route}"}, 404)
        except Exception as exc:  # noqa: BLE001
            LOG.exception("接口出错")
            self._send_json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)

    # ------------------------------------------------------- 各接口
    def _handle_chat(self) -> None:
        data = self._read_json()
        message = str(data.get("message") or "").strip()
        if not message:
            self._send_json({"ok": False, "error": "消息是空的"}, 400)
            return
        history = data.get("history") if isinstance(data.get("history"), list) else []
        cfg = load_config()
        result = ask_call(ROOT, LLMClient(cfg), message, history)
        self._send_json(result)

    def _handle_apply(self) -> None:
        data = self._read_json()
        result = apply_patch_call(
            ROOT,
            str(data.get("file") or ""),
            str(data.get("old") or ""),
            str(data.get("new") or ""),
            str(data.get("reason") or ""),
        )
        self._send_json(result)

    def _handle_pool(self) -> None:
        """返回排好序的候选池，给控制台画色块墙。"""
        data = self._read_json()
        cfg = load_config()
        store = SeenStore(ROOT / "data" / "seen.db")
        items = store.load_items(days=data.get("days") and int(data["days"]) or None)
        if not items:
            self._send_json({"ok": False, "error": "库里没有数据，先跑一次生成"})
            return
        top = int(data.get("top") or 40)
        rows = pool(items, cfg, top=top)

        # 顺便告诉前端今天实际选中的是哪一条（按现状，取手机阈值以上第一条）
        ranking = cfg.get("ranking") or {}
        th_mobile = float(ranking.get("mobile_threshold", 7.0))
        picked = next((r for r in rows if r["score"] >= th_mobile), None)

        self._send_json(
            {
                "ok": True,
                "thresholds": {
                    "mobile": th_mobile,
                    "pc": float(ranking.get("pc_threshold", 5.0)),
                },
                "total": len(items),
                "picked_key": (picked or {}).get("key", ""),
                "items": rows,
            }
        )

    def _handle_dryrun(self) -> None:
        data = self._read_json()
        cfg = load_config()
        store = SeenStore(ROOT / "data" / "seen.db")
        days = data.get("days")
        items = store.load_items(days=int(days) if days else None)
        if not items:
            self._send_json({"ok": False, "error": "库里没有数据，先跑一次生成"})
            return
        mobile = data.get("mobile")
        pc = data.get("pc")
        result = compare(
            items, cfg,
            mobile_threshold=float(mobile) if mobile not in (None, "") else None,
            pc_threshold=float(pc) if pc not in (None, "") else None,
        )
        self._send_json({"ok": True, "text": render_dryrun(result)})

    def _handle_status(self) -> None:
        cfg = load_config()
        store = SeenStore(ROOT / "data" / "seen.db")
        stats = store.stats()
        days_dir = ROOT / "output" / "days"
        day_files = sorted(days_dir.glob("day-*.json"))
        latest = day_files[-1].name if day_files else "（无）"

        import subprocess

        def git(*args: str) -> str:
            try:
                out = subprocess.run(
                    ["git", *args], cwd=str(ROOT), capture_output=True, text=True, timeout=15
                )
                return out.stdout.strip()
            except Exception:  # noqa: BLE001
                return ""

        self._send_json(
            {
                "ok": True,
                "db_total": stats["total"],
                "db_pushed": stats["pushed"],
                "latest_day_files": latest,
                "llm_on": bool(LLMClient(cfg).available),
                "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
                "git_dirty": bool(git("status", "--porcelain")),
                "git_last": git("log", "-1", "--pretty=%h %s"),
            }
        )

    # ------------------------------------------------------------ 杂项
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:  # noqa: ANN002
        sys.stdout.write(f"  · {self.address_string()} {fmt % args}\n")


def serve() -> int:
    httpd = None
    port = START_PORT
    for offset in range(MAX_TRIES):
        port = START_PORT + offset
        try:
            httpd = http.server.ThreadingHTTPServer(("0.0.0.0", port), Handler)
            break
        except OSError:
            continue
    if httpd is None:
        print(f"[ERROR] {START_PORT}-{START_PORT + MAX_TRIES - 1} 端口全被占用")
        return 1

    ip = lan_ip()
    print()
    print("=" * 66)
    print("  具身日报 · 本地服务")
    print()
    print(f"  手机答题页:  http://{ip}:{port}/web/index.html")
    print(f"  电脑控制台:  http://127.0.0.1:{port}/admin")
    print()
    print("  手机要和电脑连同一个 WiFi。")
    print("  首次可能在 Windows 防火墙弹窗，选「允许访问」。")
    print("  按 Ctrl+C 停止。")
    print("=" * 66)
    print()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s", stream=sys.stdout)
    raise SystemExit(serve())
