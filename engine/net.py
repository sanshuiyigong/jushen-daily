"""统一的网络会话。

为什么需要这个文件：

Windows 上 `urllib.request.getproxies()` 会从注册表读 IE/WinINET 的代理设置，
而 `requests` 默认 `trust_env=True` 会把它当成自己的代理。问题是注册表里
给 https 存的是 **`https://127.0.0.1:7897`**——协议头是 https。

而 xray 的本地入站是**明文 HTTP 代理**。于是 requests 会尝试对代理本身做 TLS 握手，
换来一个 `SSLZeroReturnError`。表现就是：浏览器一切正常，Python 脚本全部 SSL 失败。

所以这里的策略是：
  1. **一律关掉 trust_env**，不让环境/注册表的代理偷偷生效
  2. 需要代理的地方，显式传入 `http://` 开头的地址
  3. 谁需要代理谁显式声明，不做全局隐式行为
"""

from __future__ import annotations

import socket

import requests

# 常见的本地代理端口，按优先级探测
LOCAL_PROXY_PORTS = (7897, 7890, 7891, 10809, 10808, 1080)


def detect_local_proxy() -> str:
    """探测本机是否有正在监听的 HTTP 代理端口，有就返回 http://127.0.0.1:PORT。

    注意返回的永远是 http:// —— 即便代理支持 TLS，我们的场景也不需要，
    而且写错协议头正是上面那个坑的根源。

    GitHub Actions 的 runner 上没有这些端口，探测会失败并返回空字符串，
    所以同一个调用在云端是安全的空操作。
    """
    for port in LOCAL_PROXY_PORTS:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.35)
        try:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return f"http://127.0.0.1:{port}"
        except OSError:
            pass
        finally:
            sock.close()
    return ""


def make_session(proxy: str | None = None) -> requests.Session:
    """建一个不读环境变量的会话。

    参数 proxy:
        None       → 自动探测本地代理，探到就用
        ""         → 强制直连，不用代理
        "http://…" → 使用指定的代理
    """
    session = requests.Session()
    session.trust_env = False

    if proxy is None:
        proxy = detect_local_proxy()

    proxy = (proxy or "").strip()
    if proxy:
        if not proxy.startswith("http://") and not proxy.startswith("https://"):
            proxy = "http://" + proxy
        session.proxies = {"http": proxy, "https": proxy}

    return session


def session_proxy_of(session: requests.Session) -> str:
    """取出会话当前生效的代理地址，用于日志。"""
    return (session.proxies or {}).get("https", "")
