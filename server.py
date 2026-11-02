"""本地静态服务：让手机在同一个 WiFi 下打开页面。

只做两件事：
  /                        → 跳转到 /web/index.html
  /web/*, /output/*         → 提供静态文件

不做鉴权、不做上传。它只在局域网里活几分钟，用完关掉即可。
"""

from __future__ import annotations

import http.server
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
START_PORT = 8000
MAX_TRIES = 10


def lan_ip() -> str:
    """取本机在局域网里的地址。UDP connect 不会真的发包。"""
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

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/web/index.html")
            self.end_headers()
            return
        super().do_GET()

    def end_headers(self) -> None:
        # 手机浏览器缓存很顽固，开发期一律不缓存
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
    print("=" * 62)
    print("  具身日报 · 本地服务已启动")
    print()
    print(f"  手机请访问:  http://{ip}:{port}/web/index.html")
    print(f"  本机预览:    http://127.0.0.1:{port}/web/index.html")
    print()
    print("  手机要和电脑连同一个 WiFi。")
    print("  首次可能在 Windows 防火墙弹窗，选「允许访问」。")
    print("  按 Ctrl+C 停止。")
    print("=" * 62)
    print()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
