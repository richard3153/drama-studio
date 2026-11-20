"""Ollama 适配器：剧本/拆解/续写走本地 LLM。"""
import json
import re

import httpx

from ..config import OLLAMA_URL

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think(text: str) -> str:
    """qwen3 思考模式输出剥离 <think>...</think>。"""
    return _THINK_RE.sub("", text).strip()


class OllamaAdapter:
    def __init__(self, base_url: str = OLLAMA_URL):
        self.base = base_url.rstrip("/")

    async def chat(self, prompt: str, *, system: str = "", model: str = "qwen3.5:4b",
                   json_mode: bool = False, temperature: float = 0.7,
                   timeout: float = 600.0, num_ctx: int = 8192,
                   disable_think: bool = True) -> str:
        payload = {
            "model": model,
            "stream": False,
            "messages": ([{"role": "system", "content": system}] if system else [])
            + [{"role": "user", "content": prompt}],
            "options": {"temperature": temperature, "num_ctx": num_ctx},
        }
        if json_mode:
            payload["format"] = "json"
        if disable_think:
            payload["think"] = False  # 新版 Ollama 支持关闭思考模式；旧版会忽略/报错则走降级
        try:
            content = await self._post_chat(payload, timeout)
        except httpx.HTTPStatusError as e:
            if disable_think and e.response.status_code == 400:
                payload.pop("think", None)
                content = await self._post_chat(payload, timeout)
            else:
                raise
        if json_mode:
            json.loads(_strip_think(content))  # 校验，失败抛异常由上层重试
        return content

    async def _post_chat(self, payload: dict, timeout: float) -> str:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(f"{self.base}/api/chat", json=payload)
            r.raise_for_status()
            return r.json()["message"]["content"]

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{self.base}/api/tags")
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
