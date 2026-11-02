"""LLM 客户端（DeepSeek，OpenAI 兼容接口）。

设计原则：**没有 key 不是错误状态。**
拿不到 key、网络断了、额度用完、返回的不是合法 JSON —— 一律返回 None，
调用方自动走模板降级路径。整个系统在任何时候都能跑。

key 的读取顺序：
  1. 环境变量 JUSHEN_LLM_KEY   ← 推荐，不会进 git，云上也能用
  2. config.yaml 里的 llm.api_key
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests

from .net import make_session

LOG = logging.getLogger("llm")

ENV_KEY = "JUSHEN_LLM_KEY"


def _key_from_windows_registry(name: str) -> str:
    """从用户级环境变量（注册表 HKCU\\Environment）读 key。

    为什么需要这个：在 Windows 上用 setx 设置的环境变量，只对「之后新建的进程」
    生效，而且资源管理器会缓存启动时的环境块。如果 DSH / cmd 是在设置之前启动的，
    os.environ 里根本看不到这个变量，但注册表里已经有了。
    """
    try:
        import winreg  # 只有 Windows 有
    except ImportError:
        return ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as hkey:
            value, _ = winreg.QueryValueEx(hkey, name)
            return str(value or "")
    except OSError:
        return ""


def _resolve_api_key(conf: dict[str, Any]) -> str:
    """三级兜底：进程环境变量 → Windows 用户注册表 → config.yaml。"""
    for candidate in (
        os.environ.get(ENV_KEY),
        _key_from_windows_registry(ENV_KEY),
        conf.get("api_key"),
    ):
        text = str(candidate or "").strip()
        if text:
            return text
    return ""


def _extract_json(text: str) -> dict[str, Any] | None:
    """从模型回复里抠出第一个完整 JSON 对象。容忍 ```json 围栏和前后废话。"""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # 去掉 ```json ... ```
        lines = [ln for ln in cleaned.splitlines() if not ln.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    start = cleaned.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(cleaned[start : i + 1])
                except json.JSONDecodeError:
                    return None
                return obj if isinstance(obj, dict) else None
    return None


class LLMClient:
    def __init__(self, cfg: dict[str, Any]):
        conf = cfg.get("llm") or {}
        self.api_key = _resolve_api_key(conf)
        self.base_url = str(conf.get("base_url") or "https://api.deepseek.com").rstrip("/")
        self.model = str(conf.get("model") or "deepseek-chat")
        self.timeout = int(conf.get("timeout") or 90)
        self._calls = 0
        # DeepSeek 是国内服务，直连最快。强制不走代理，
        # 避免 requests 从注册表读到带 https:// 协议头的错误代理配置。
        self.session = make_session(proxy="")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @property
    def calls(self) -> int:
        return self._calls

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.4,
        max_tokens: int = 1400,
        json_mode: bool = False,
    ) -> str | None:
        if not self.available:
            return None
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            self._calls += 1
            resp = self.session.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                LOG.warning("LLM 返回 %s：%s", resp.status_code, resp.text[:200])
                return None
            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                LOG.warning("LLM 返回里没有 choices")
                return None
            return (choices[0].get("message") or {}).get("content")
        except Exception as exc:  # noqa: BLE001
            LOG.warning("LLM 调用失败：%s", exc)
            return None

    def chat_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 1400,
    ) -> dict[str, Any] | None:
        text = self.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        if not text:
            return None
        obj = _extract_json(text)
        if obj is None:
            LOG.warning("LLM 回复不是合法 JSON，已忽略")
        return obj


def _mask(text: str) -> str:
    if not text:
        return "(空)"
    if len(text) <= 12:
        return text[:3] + "***"
    return f"{text[:8]}…{text[-4:]}"


if __name__ == "__main__":
    import sys

    from .config import load_config

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s", stream=sys.stdout)
    cfg = load_config()
    client = LLMClient(cfg)
    print(f"key      : {_mask(client.api_key)}")
    print(f"base_url : {client.base_url}")
    print(f"model    : {client.model}")
    print(f"available: {client.available}")

    if not client.available:
        print("\n没有 key，跳过实测。")
        raise SystemExit(0)

    print("\n===== 实测调用 =====")
    reply = client.chat(
        [
            {"role": "system", "content": "你在做连通性测试。"},
            {"role": "user", "content": "只回复两个字：收到"},
        ],
        temperature=0,
        max_tokens=20,
    )
    print(f"回复: {reply!r}")

    print("\n===== 实测 JSON 模式 =====")
    obj = client.chat_json(
        "你只输出 JSON，不要任何其他文字。",
        '返回 {"ok": true, "value": 42}',
        temperature=0,
        max_tokens=60,
    )
    print(f"解析结果: {obj}")
    print(f"\n累计调用 {client.calls} 次")
