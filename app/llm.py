"""LLM 客户端。

只依赖 OpenAI 兼容的 /chat/completions 协议，所以智谱、硅基流动、DeepSeek、
Ollama、OpenAI 都能用同一份代码 —— 换供应商只改 .env。

初版把 api_key 硬编码在源码里，且用的是当时 langchain 的 `chat([...])` 调用式，
新版 langchain 已经把那个入口删了，这也是项目跑不起来的直接原因之一。
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from openai import BadRequestError, OpenAI

from .config import settings

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class EmptyCompletion(RuntimeError):
    """模型返回了空正文。单独立一个异常，方便上层区分"模型没说话"和"说的不是 JSON"。"""


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0

    def add(self, other: "Usage") -> None:
        self.calls += other.calls
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.seconds += other.seconds

    def snapshot(self) -> "Usage":
        return Usage(self.calls, self.prompt_tokens, self.completion_tokens, self.seconds)

    def since(self, base: "Usage") -> "Usage":
        return Usage(
            self.calls - base.calls,
            self.prompt_tokens - base.prompt_tokens,
            self.completion_tokens - base.completion_tokens,
            self.seconds - base.seconds,
        )

    def __str__(self) -> str:
        return (
            f"{self.calls} 次调用 / {self.prompt_tokens} prompt tok / "
            f"{self.completion_tokens} completion tok / {self.seconds:.2f}s"
        )


@dataclass
class LLMClient:
    # 用 default_factory 而不是 `= settings.llm_model`：后者在 import 阶段就求值，
    # 之后再改环境变量或调 reload_settings() 都不会生效（config.py 里修过同一个坑）。
    model: str = field(default_factory=lambda: settings.llm_model)
    usage: Usage = field(default_factory=Usage)

    def __post_init__(self) -> None:
        settings.require_llm()
        self._client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout,
            max_retries=2,
        )

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int | None = 2048,
        thinking: bool | None = None,
    ) -> str:
        """thinking=None 表示不干预（用供应商默认），True/False 显式开关思维链。

        GLM-4.5 / Qwen3 这类混合推理模型默认会先输出一大段思维链。实测回答
        「连通」两个字花了 176 个 completion token，关掉只要 2 个。开关放这里，
        由调用方按任务决定：生成 Cypher 可能值得想一想，组织回答完全不需要。
        """
        extra: dict = {}
        if thinking is not None:
            # 智谱的参数形态；其他供应商不认识时会报 400，下面有降级
            extra["thinking"] = {"type": "enabled" if thinking else "disabled"}

        t0 = time.perf_counter()
        try:
            resp = self._create(messages, temperature, max_tokens, extra)
        except BadRequestError:
            if not extra:
                raise
            # 供应商不支持 thinking 参数，去掉重试一次，别为了省 token 把功能搞挂
            resp = self._create(messages, temperature, max_tokens, {})
        elapsed = time.perf_counter() - t0

        u = getattr(resp, "usage", None)
        self.usage.add(
            Usage(
                calls=1,
                prompt_tokens=getattr(u, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(u, "completion_tokens", 0) or 0,
                seconds=elapsed,
            )
        )
        message = resp.choices[0].message
        content = (message.content or "").strip()
        if not content:
            # 思维链把 max_tokens 吃光了，正文一个字没吐出来。这种情况必须报出来，
            # 否则表现成"模型返回的不是合法 JSON"，排查方向会被带偏。
            reasoning = getattr(message, "reasoning_content", None)
            finish = resp.choices[0].finish_reason
            raise EmptyCompletion(
                f"模型没有返回正文（finish_reason={finish}，"
                f"思维链 {len(reasoning or '')} 字）。调大 max_tokens 或关闭 thinking。"
            )
        return content

    def _create(self, messages, temperature, max_tokens, extra):
        return self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **({"extra_body": extra} if extra else {}),
        )

    def chat_json(
        self, messages: list[dict], temperature: float = 0.0, thinking: bool | None = None
    ) -> dict:
        """要求模型返回 JSON。免费小模型经常裹 ```json 或带 <think>，这里统一剥掉。"""
        raw = self.chat(messages, temperature=temperature, thinking=thinking)
        return parse_json(raw)


def parse_json(raw: str) -> dict:
    text = _THINK.sub("", raw).strip()
    if m := _JSON_BLOCK.search(text):
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 兜底：抓第一个平衡的 {...}
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            depth += (ch == "{") - (ch == "}")
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    break
    raise ValueError(f"模型没有返回合法 JSON：{raw[:300]}")
