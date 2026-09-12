"""集中配置。所有密钥只从环境变量 / .env 读取，绝不写进代码。

v2 相对 v1 的两处结构性改动：
  * 配置在**实例化时**读环境变量，不再在 class 体里读。v1 写的是
    `neo4j_uri: str = os.getenv(...)`，那行代码在 import 阶段就执行完了，
    之后再改环境变量（测试里最常见）也不会生效，还会让单测互相污染。
  * 新增的行为开关都能从 .env 关掉，方便做 A/B 评测（快路径开/关、安全闸开/关）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

load_dotenv(ROOT / ".env")


def _env(key: str, default: str) -> str:
    return os.getenv(key, default).strip()


def _bool(key: str, default: bool = False) -> bool:
    return _env(key, str(default)).lower() in ("1", "true", "yes", "on")


def _int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def _float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


def _find_medical_json() -> str:
    """定位 45MB 的疾病数据集。

    查找顺序：环境变量 MEDICAL_JSON -> 仓库根目录 -> 上一级目录。
    上一级那条是为了让本仓库能作为子目录嵌在别的工作区里直接跑（开发时很方便），
    找不到也不报错 —— 调用方（scripts/load_kg.py）会给出带下载链接的提示。

    数据不随仓库分发，原因见 NOTICE.md。
    """
    if env := _env("MEDICAL_JSON", ""):
        return env
    for base in (ROOT, ROOT.parent):
        if (p := base / "medical.json").exists():
            return str(p)
    return str(ROOT / "medical.json")


def _find_neo4j_home() -> str:
    """定位 Neo4j 发行版。顺序同上：NEO4J_HOME -> 仓库根 -> 上一级。

    发行版不随仓库分发（社区版约 460MB，GPLv3），请自行下载解压到 neo4j/ 下。
    """
    if env := _env("NEO4J_HOME", ""):
        return env
    for base in (ROOT, ROOT.parent):
        d = base / "neo4j"
        if d.is_dir():
            for child in sorted(d.glob("neo4j-community-*")):
                return str(child)
    return ""


@dataclass(frozen=True)
class Settings:
    # ---- Neo4j ----
    neo4j_uri: str = field(default_factory=lambda: _env("NEO4J_URI", "bolt://127.0.0.1:7687"))
    neo4j_user: str = field(default_factory=lambda: _env("NEO4J_USER", "neo4j"))
    neo4j_password: str = field(default_factory=lambda: _env("NEO4J_PASSWORD", ""))
    neo4j_database: str = field(default_factory=lambda: _env("NEO4J_DATABASE", "neo4j"))

    # ---- LLM（任何 OpenAI 兼容端点：智谱 / 硅基流动 / DeepSeek / Ollama / OpenAI）----
    llm_base_url: str = field(
        default_factory=lambda: _env("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    )
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", "glm-4.5-flash"))
    llm_timeout: float = field(default_factory=lambda: _float("LLM_TIMEOUT", 60))
    # 思维链开关：auto=不干预供应商默认，on/off=显式指定。默认 off，理由见 README 的实测对比。
    llm_thinking: str = field(default_factory=lambda: _env("LLM_THINKING", "off").lower())

    # ---- 检索行为 ----
    max_cypher_retries: int = field(default_factory=lambda: _int("MAX_CYPHER_RETRIES", 3))
    default_limit: int = field(default_factory=lambda: _int("DEFAULT_LIMIT", 25))
    # LIMIT 上限。v1 只检查"结尾有没有 LIMIT"，模型写 LIMIT 100000 照样放行，
    # 一条语句就能把 2.8 万节点全拖回来。
    max_limit: int = field(default_factory=lambda: _int("MAX_LIMIT", 200))
    # 变长路径上限。`[*]` 在 33 万条关系的图上会直接把服务器打爆。
    max_path_hops: int = field(default_factory=lambda: _int("MAX_PATH_HOPS", 3))
    query_timeout_s: float = field(default_factory=lambda: _float("QUERY_TIMEOUT_S", 10))
    trace: bool = field(default_factory=lambda: _bool("TRACE", True))

    # ---- v2 新增开关（都能关掉，方便做对照评测）----
    # 模板快路径：常见单跳问题不调 LLM，直接用白名单模板出 Cypher
    fast_path: bool = field(default_factory=lambda: _bool("FAST_PATH", True))
    # 医疗安全闸：急症提示、剂量拒答、危机干预
    safety: bool = field(default_factory=lambda: _bool("SAFETY", True))
    # 0 结果时用全文索引 + 近似名做兜底检索
    fallback_search: bool = field(default_factory=lambda: _bool("FALLBACK_SEARCH", True))
    # 多轮对话记忆的轮数（0 = 关闭多轮）
    history_turns: int = field(default_factory=lambda: _int("HISTORY_TURNS", 4))
    # 问答结果缓存
    cache_enabled: bool = field(default_factory=lambda: _bool("CACHE", True))
    cache_ttl_s: float = field(default_factory=lambda: _float("CACHE_TTL_S", 3600))

    # ---- 路径 ----
    medical_json: str = field(default_factory=_find_medical_json)
    neo4j_home: str = field(default_factory=_find_neo4j_home)

    @property
    def thinking(self) -> bool | None:
        return {"on": True, "off": False}.get(self.llm_thinking)

    def require_llm(self) -> None:
        if not self.llm_api_key:
            raise RuntimeError(
                "缺少 LLM_API_KEY。请复制 .env.example 为 .env 并填入密钥，"
                "或用 --mock 跑离线链路。"
            )

    def require_neo4j(self) -> None:
        if not self.neo4j_password:
            raise RuntimeError("缺少 NEO4J_PASSWORD。请在 .env 中配置。")

    def redacted(self) -> dict:
        """打印配置时用。密钥只留前 4 位 —— trace / 日志 / 报错都可能被贴到别处去。"""
        def mask(v: str) -> str:
            return f"{v[:4]}…({len(v)} 位)" if v else "(未设置)"

        return {
            "neo4j_uri": self.neo4j_uri,
            "neo4j_user": self.neo4j_user,
            "neo4j_password": mask(self.neo4j_password),
            "neo4j_database": self.neo4j_database,
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "llm_api_key": mask(self.llm_api_key),
            "llm_thinking": self.llm_thinking,
            "fast_path": self.fast_path,
            "safety": self.safety,
            "fallback_search": self.fallback_search,
            "history_turns": self.history_turns,
            "max_limit": self.max_limit,
            "query_timeout_s": self.query_timeout_s,
        }


settings = Settings()


def reload_settings() -> Settings:
    """重新读一遍环境变量，**就地更新**已有的 settings 对象。

    不能写成 `global settings; settings = Settings()`。
    各模块都是 `from .config import settings` —— 那是一次性的**名字绑定**，
    重新赋值只换掉 config 这一个模块里的名字，text2cypher / graph / planner
    手里拿的还是旧对象。

    这个坑很阴：`--no-fast-path` 会照常打印"已关闭"，评测也照常跑完出报表，
    但管线里读到的 `settings.fast_path` 一直是 True，两组对照数据其实是同一组。
    静默失效的开关比报错的开关危险得多。

    所以改成逐字段就地写回。dataclass 是 frozen 的，用 object.__setattr__ 绕过，
    这是唯一一处刻意破坏不可变性的地方 —— 换来的是"所有持有者立刻看到新值"。
    """
    fresh = Settings()
    for f in fields(fresh):
        object.__setattr__(settings, f.name, getattr(fresh, f.name))
    return settings
