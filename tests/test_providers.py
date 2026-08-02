"""Provider 层 — 重试、超时、错误归一化、工厂装配。

不触网：OpenAI 客户端被替换为可编排的假对象；退避 sleep 被打桩以保持测试秒级。
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest
from openai import APITimeoutError

from pet_generator.config.settings import ClassifierSettings, ProviderSettings
from pet_generator.providers import (
    create_image_provider,
    create_video_provider,
    create_vision_provider,
)
from pet_generator.providers.base import GenerationResult
from pet_generator.providers.vision.openai_compatible import OpenAICompatibleVisionProvider


class ScriptedCompletions:
    """按脚本依次返回内容或抛异常，并记录调用次数。"""

    def __init__(self, script: list):
        self._script = list(script)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        item = self._script.pop(0) if self._script else self._script_default()
        if isinstance(item, Exception):
            raise item
        message = types.SimpleNamespace(content=item)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    @staticmethod
    def _script_default():
        return '{"body_type": "humanoid"}'


def _provider(script: list, monkeypatch, *, max_retries: int = 2) -> tuple:
    settings = ClassifierSettings()
    settings.max_retries = max_retries
    provider = OpenAICompatibleVisionProvider(settings)
    completions = ScriptedCompletions(script)
    provider._client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=completions))
    # 屏蔽指数退避，保持测试秒级
    monkeypatch.setattr(
        "pet_generator.providers.vision.openai_compatible.time.sleep", lambda s: None
    )
    return provider, completions


@pytest.fixture
def image_file(portraits: Path) -> Path:
    return portraits / "figure_anime_b.png"


# ---------------------------------------------------------------------------
# classify 重试语义
# ---------------------------------------------------------------------------


def test_first_attempt_success_makes_one_call(monkeypatch, image_file: Path):
    provider, completions = _provider(['{"body_type": "quadruped"}'], monkeypatch)
    assert provider.classify(image_file, "sys", "user") == {"body_type": "quadruped"}
    assert completions.calls == 1


def test_malformed_json_is_retried(monkeypatch, image_file: Path):
    provider, completions = _provider(["not json", '{"body_type": "humanoid"}'], monkeypatch)
    assert provider.classify(image_file, "sys", "user")["body_type"] == "humanoid"
    assert completions.calls == 2


def test_timeout_is_retried_then_reported(monkeypatch, image_file: Path):
    timeout = APITimeoutError(request=None)  # type: ignore[arg-type]
    provider, completions = _provider([timeout, timeout, timeout], monkeypatch, max_retries=2)
    result = provider.classify(image_file, "sys", "user")
    assert completions.calls == 3, "总尝试 = 1 + max_retries"
    assert "timed out" in result["error"]
    assert "All 3 attempts failed" in result["error"]


def test_empty_content_is_retried(monkeypatch, image_file: Path):
    provider, completions = _provider([None, '{"body_type": "object"}'], monkeypatch)
    assert provider.classify(image_file, "sys", "user")["body_type"] == "object"
    assert completions.calls == 2


def test_non_object_json_is_rejected(monkeypatch, image_file: Path):
    provider, completions = _provider(["[1, 2, 3]", "[4]", "[5]"], monkeypatch, max_retries=2)
    result = provider.classify(image_file, "sys", "user")
    assert "error" in result
    assert completions.calls == 3


def test_missing_image_fails_fast_without_retry(monkeypatch, tmp_path: Path):
    """文件不存在属于调用方错误，重试没有意义。"""
    provider, completions = _provider(['{"body_type": "humanoid"}'], monkeypatch)
    result = provider.classify(tmp_path / "absent.png", "sys", "user")
    assert "error" in result
    assert completions.calls == 0


def test_describe_returns_text(monkeypatch, image_file: Path):
    provider, _ = _provider(["a small figure"], monkeypatch)
    assert provider.describe(image_file) == "a small figure"


# ---------------------------------------------------------------------------
# 工厂装配
# ---------------------------------------------------------------------------


def test_vision_factory_returns_openai_compatible():
    provider = create_vision_provider(ClassifierSettings())
    assert isinstance(provider, OpenAICompatibleVisionProvider)


@pytest.mark.parametrize("name", ["azure", "bailian"])
def test_image_factory_known_providers(name: str):
    provider = create_image_provider(name, ProviderSettings())
    assert hasattr(provider, "edit") and hasattr(provider, "generate")


@pytest.mark.parametrize("name", ["kling", "wan27"])
def test_video_factory_known_providers(name: str):
    provider = create_video_provider(name, ProviderSettings())
    assert hasattr(provider, "image_to_video")


def test_unknown_provider_name_raises():
    with pytest.raises((ValueError, KeyError)):
        create_image_provider("nonexistent-provider", ProviderSettings())


def test_generation_result_bool_and_first_path(tmp_path: Path):
    ok = GenerationResult(success=True, output_paths=[tmp_path / "a.png"])
    assert bool(ok) is True
    assert ok.first_path == tmp_path / "a.png"

    failed = GenerationResult(success=False, error="nope")
    assert bool(failed) is False
    assert failed.first_path is None
