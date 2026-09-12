"""配置层的单元测试。

这一组存在的理由很具体：配置出错是**静默**的。
`--no-fast-path` 会照常打印"已关闭"、评测会照常跑完出报表，
只是管线里读到的开关一直没变，两组对照数据其实是同一组。
比起报错，这种失效方式危险得多，所以要用测试钉死。
"""
from __future__ import annotations

import os

import pytest

from app.config import Settings, reload_settings, settings


@pytest.fixture(autouse=True)
def restore_env():
    """每个用例跑完把环境变量和 settings 恢复原状，避免互相污染。"""
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)
    reload_settings()


class TestReadsEnvAtInstantiation:
    def test_env_change_takes_effect(self):
        """v1 写的是 `x: str = os.getenv(...)`，那行在 import 阶段就求值完了，
        之后改环境变量根本不生效 —— 单测里会表现成用例之间互相污染。"""
        os.environ["DEFAULT_LIMIT"] = "7"
        assert Settings().default_limit == 7

    def test_bad_int_falls_back_to_default(self):
        os.environ["DEFAULT_LIMIT"] = "不是数字"
        assert Settings().default_limit == 25

    def test_bad_float_falls_back_to_default(self):
        os.environ["QUERY_TIMEOUT_S"] = "abc"
        assert Settings().query_timeout_s == 10.0

    @pytest.mark.parametrize("raw,want", [
        ("true", True), ("True", True), ("1", True), ("yes", True), ("on", True),
        ("false", False), ("0", False), ("no", False), ("随便什么", False),
    ])
    def test_bool_parsing(self, raw, want):
        os.environ["FAST_PATH"] = raw
        assert Settings().fast_path is want


class TestReloadPropagates:
    def test_reload_mutates_the_shared_instance(self):
        """所有模块都是 `from .config import settings`（一次性名字绑定）。
        reload 必须**就地改**这个对象，重新赋值只会换掉 config 自己那个名字。"""
        import app.text2cypher as t2c

        assert t2c.settings is settings, "管线拿到的必须是同一个 settings 对象"

        os.environ["FAST_PATH"] = "false"
        reload_settings()
        assert settings.fast_path is False
        assert t2c.settings.fast_path is False, "开关没传到管线里 —— A/B 对照会静默失效"

        os.environ["FAST_PATH"] = "true"
        reload_settings()
        assert t2c.settings.fast_path is True

    def test_reload_returns_same_object(self):
        assert reload_settings() is settings

    def test_all_pipeline_modules_share_one_settings(self):
        import app.answer  # noqa: F401
        import app.graph as graph
        import app.llm as llm
        import app.text2cypher as t2c

        for mod in (graph, llm, t2c):
            assert mod.settings is settings, mod.__name__


class TestRedaction:
    def test_secrets_are_masked(self):
        os.environ["LLM_API_KEY"] = "sk-1234567890abcdef"
        os.environ["NEO4J_PASSWORD"] = "hunter2hunter2"
        out = Settings().redacted()
        assert "sk-1234567890abcdef" not in str(out)
        assert "hunter2hunter2" not in str(out)
        assert out["llm_api_key"].startswith("sk-1")

    def test_unset_secret_says_so(self):
        os.environ["LLM_API_KEY"] = ""
        assert Settings().redacted()["llm_api_key"] == "(未设置)"

    def test_non_secret_fields_are_visible(self):
        out = Settings().redacted()
        assert out["neo4j_uri"].startswith("bolt://")


class TestRequire:
    def test_require_llm_raises_without_key(self):
        os.environ["LLM_API_KEY"] = ""
        with pytest.raises(RuntimeError, match="LLM_API_KEY"):
            Settings().require_llm()

    def test_require_neo4j_raises_without_password(self):
        os.environ["NEO4J_PASSWORD"] = ""
        with pytest.raises(RuntimeError, match="NEO4J_PASSWORD"):
            Settings().require_neo4j()


class TestThinking:
    @pytest.mark.parametrize("raw,want", [("on", True), ("off", False), ("auto", None)])
    def test_tristate(self, raw, want):
        os.environ["LLM_THINKING"] = raw
        assert Settings().thinking is want


class TestPaths:
    def test_medical_json_falls_back_to_parent_dir(self):
        """v2 是原项目的子目录，47MB 的数据文件不复制一份。"""
        from pathlib import Path

        p = Path(Settings().medical_json)
        assert p.name == "medical.json"
