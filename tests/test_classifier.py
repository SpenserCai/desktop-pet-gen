"""Stage 0 分类 — 真实响应解析、字段校验、重试与降级。

「成功路径」用录制的真实 AI 响应（`fixtures/ai_pipeline/classification.json`），
「异常路径」用构造的畸形响应，两者都不触网。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pet_generator.config.classifier_config import ClassifierConfig
from pet_generator.stages.classifier import ClassificationResult, Classifier
from tests.support.fakes import ReplayVisionProvider


def _classifier(vision, *, max_retries: int = 1, fallback: str = "humanoid") -> Classifier:
    config = ClassifierConfig()
    config.max_retries = max_retries
    config.fallback_body_type = fallback
    return Classifier(vision, config)


# ---------------------------------------------------------------------------
# 成功路径：回放真实响应
# ---------------------------------------------------------------------------


def test_recorded_response_maps_to_result(ai_assets: Path, portraits: Path, tmp_path: Path):
    """真实录制响应应被完整映射，且中文字段不被转义写盘。"""
    vision = ReplayVisionProvider(ai_assets / "classification.json")
    result = _classifier(vision).run(portraits / "figure_anime_a.png", tmp_path)

    assert result.body_type == "humanoid"
    assert result.subject_category == "non_living"
    assert result.input_material == "photo_figure"
    assert result.style_target == "chibi_anime"
    assert result.confidence == pytest.approx(0.99)
    assert "粉色短发" in result.key_features
    assert result.color_palette[0].startswith("#")

    saved = (tmp_path / "result.json").read_text(encoding="utf-8")
    assert "粉色短发" in saved, "中文必须原样写盘（ensure_ascii=False）"
    assert json.loads(saved)["body_type"] == "humanoid"


# ---------------------------------------------------------------------------
# 异常路径
# ---------------------------------------------------------------------------


def test_provider_error_dict_triggers_fallback(portraits: Path, tmp_path: Path):
    """provider 返回 {"error": ...} 时耗尽重试并降级，且仍持久化结果。"""
    vision = ReplayVisionProvider(raw_override={"error": "boom"})
    result = _classifier(vision, max_retries=2, fallback="quadruped").run(
        portraits / "figure_anime_a.png", tmp_path
    )

    assert result.body_type == "quadruped"
    assert "fallback after 3 failures" in result.reasoning
    assert len(vision.calls) == 3, "总尝试次数应为 1 + max_retries"
    assert (tmp_path / "result.json").exists()


def test_invalid_body_type_is_rejected_then_fallback(portraits: Path, tmp_path: Path):
    """非法 body_type 不得进入下游（下游是闭合的 Rust 枚举）。"""
    vision = ReplayVisionProvider(raw_override={"body_type": "dragonoid", "confidence": 1.0})
    result = _classifier(vision, max_retries=0).run(portraits / "figure_anime_a.png", tmp_path)
    assert result.body_type == "humanoid"
    assert result.reasoning.startswith("fallback after 1 failures")


def test_provider_exception_is_caught(portraits: Path, tmp_path: Path):
    """provider 抛异常（违反契约）时也不得让管线崩溃。"""
    vision = ReplayVisionProvider(fail_times=99)
    result = _classifier(vision, max_retries=1).run(portraits / "figure_anime_a.png", tmp_path)
    assert result.body_type == "humanoid"
    assert "Provider 异常" in result.reasoning


def test_retry_then_success(ai_assets: Path, portraits: Path, tmp_path: Path):
    """首次失败、第二次成功时应采用成功结果而不是降级。"""
    vision = ReplayVisionProvider(ai_assets / "classification.json", fail_times=1)
    result = _classifier(vision, max_retries=2).run(portraits / "figure_anime_a.png", tmp_path)
    assert result.body_type == "humanoid"
    assert result.confidence == pytest.approx(0.99)
    assert len(vision.calls) == 2


# ---------------------------------------------------------------------------
# 数据结构容错
# ---------------------------------------------------------------------------


def test_from_dict_tolerates_extra_and_missing_fields():
    result = ClassificationResult.from_dict(
        {
            "subject_category": "living",
            "body_type": "quadruped",
            "input_material": "illustration",
            "style_target": "pixel",
            "unexpected_field": 42,
        }
    )
    assert result.body_type == "quadruped"
    assert result.key_features == []
    assert result.confidence == 0.0


def test_default_marks_object_as_non_living():
    assert ClassificationResult.default("object").subject_category == "non_living"
    assert ClassificationResult.default("limbless").subject_category == "living"


def test_to_dict_roundtrip():
    original = ClassificationResult.default("quadruped")
    assert ClassificationResult.from_dict(original.to_dict()) == original
