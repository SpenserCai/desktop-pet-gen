"""Stage 0: 智能分类 — 分析输入图片的体型、材质与目标风格。

使用视觉理解 Provider（Vision LLM）对输入图片进行结构化分类，
输出 ``ClassificationResult``，驱动后续所有阶段的 prompt 选择。

容错策略:
- JSON 解析 / 校验失败 → 重试（最多 ``config.max_retries`` 次）
- 全部重试失败 → 降级为 ``ClassificationResult.default(fallback_body_type)``
- 置信度低于阈值 → 打印警告，继续执行（不阻塞管线）

持久化:
- 分类结果写入 ``output_dir/result.json``，便于断点续跑与调试。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pet_generator.config.classifier_config import ClassifierConfig
from pet_generator.providers.base import VisionProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class ClassificationResult:
    """分类阶段的结构化输出。

    Attributes:
        subject_category: "living" | "non_living"
        body_type: "humanoid" | "quadruped" | "limbless" | "object"
        input_material: 输入素材材质
        style_target: 推荐目标风格
        key_features: 关键视觉特征列表
        color_palette: 主色调 hex 列表
        confidence: 整体置信度 [0, 1]
        reasoning: 分类理由（一句话）
        raw_response: 原始 LLM 响应文本（调试用）
    """

    subject_category: str  # "living" | "non_living"
    body_type: str  # "humanoid" | "quadruped" | "limbless" | "object"
    input_material: (
        str  # "photo_real" | "photo_figure" | "pixel_art" | "illustration" | "3d_render"
    )
    style_target: str  # "chibi_anime" | "flat_cartoon" | "pixel" | "clay" | "keep_original"
    key_features: list[str] = field(default_factory=list)
    color_palette: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""
    raw_response: str = ""

    # -- 工厂方法 ----------------------------------------------------------

    @classmethod
    def default(cls, body_type: str = "humanoid") -> ClassificationResult:
        """手动指定 body_type 时的默认结果（降级 / 用户覆盖）。"""
        return cls(
            subject_category="living" if body_type != "object" else "non_living",
            body_type=body_type,
            input_material="illustration",
            style_target="keep_original",
            confidence=1.0,
            reasoning="manually specified",
        )

    @classmethod
    def from_dict(cls, data: dict) -> ClassificationResult:
        """从字典构建（容忍多余 / 缺失字段）。"""
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    # -- 序列化 ------------------------------------------------------------

    def to_dict(self) -> dict:
        """转为可 JSON 序列化的字典。"""
        return asdict(self)


# ---------------------------------------------------------------------------
# Stage 实现
# ---------------------------------------------------------------------------


class Classifier:
    """Stage 0 — 智能分类器。

    Args:
        vision_provider: 视觉理解 Provider（已初始化）。
        config: 分类器领域配置；为 None 时使用默认配置。
    """

    def __init__(
        self,
        vision_provider: VisionProvider,
        config: ClassifierConfig | None = None,
    ) -> None:
        self._vision = vision_provider
        self._config = config or ClassifierConfig()

    # -- 公开接口 ----------------------------------------------------------

    def run(self, input_image: Path, output_dir: Path) -> ClassificationResult:
        """执行分类，持久化结果到 ``output_dir/result.json``。

        Args:
            input_image: 待分类的输入图片路径。
            output_dir: 输出目录（不存在时自动创建）。

        Returns:
            ClassificationResult — 成功时为 LLM 分类结果，
            全部重试失败后降级为默认值。
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        result = self._classify_with_retry(input_image)

        # 置信度检查（仅警告，不阻塞）
        if not self._config.is_confident(result.to_dict()):
            logger.warning(
                "分类置信度 %.2f 低于阈值 %.2f，结果可能不够准确: %s",
                result.confidence,
                self._config.confidence_threshold,
                result.reasoning,
            )

        # 持久化
        result_path = output_dir / "result.json"
        result_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("分类结果已保存: %s (body_type=%s)", result_path, result.body_type)
        return result

    # -- 内部方法 ----------------------------------------------------------

    def _classify_with_retry(self, input_image: Path) -> ClassificationResult:
        """带重试的分类调用。

        重试次数由 ``config.max_retries`` 控制（总尝试 = 1 + max_retries）。
        全部失败后降级为默认分类。
        """
        max_attempts = 1 + self._config.max_retries
        last_error = ""

        for attempt in range(1, max_attempts + 1):
            logger.info("分类尝试 %d/%d ...", attempt, max_attempts)
            try:
                raw = self._vision.classify(
                    input_image,
                    system_prompt=self._config.system_prompt,
                    user_prompt=self._config.user_prompt,
                )
            except Exception as exc:  # noqa: BLE001 — Provider 层理应不抛，但防御性兜底
                last_error = f"Provider 异常: {exc}"
                logger.warning("分类调用异常 (attempt %d): %s", attempt, exc)
                continue

            # VisionProvider.classify 失败时返回 {"error": "..."}
            if "error" in raw:
                last_error = raw["error"]
                logger.warning("分类返回错误 (attempt %d): %s", attempt, last_error)
                continue

            # 校验字段合法性
            is_valid, err_msg = self._config.validate_result(raw)
            if not is_valid:
                last_error = err_msg
                logger.warning("分类结果校验失败 (attempt %d): %s", attempt, err_msg)
                continue

            # 成功 — 构建结构化结果
            result = self._build_result(raw)
            logger.info(
                "分类成功: body_type=%s, input_material=%s, style_target=%s, confidence=%.2f",
                result.body_type,
                result.input_material,
                result.style_target,
                result.confidence,
            )
            return result

        # 全部失败 → 降级
        logger.error(
            "分类全部 %d 次尝试失败，降级为默认 body_type='%s'。最后错误: %s",
            max_attempts,
            self._config.fallback_body_type,
            last_error,
        )
        fallback = ClassificationResult.default(self._config.fallback_body_type)
        fallback.reasoning = f"fallback after {max_attempts} failures: {last_error}"
        return fallback

    @staticmethod
    def _build_result(raw: dict) -> ClassificationResult:
        """将 VisionProvider 返回的原始字典映射为 ClassificationResult。"""
        body_type = raw.get("body_type", "humanoid")
        subject_category = raw.get(
            "subject_category",
            "non_living" if body_type == "object" else "living",
        )
        return ClassificationResult(
            subject_category=subject_category,
            body_type=body_type,
            input_material=raw.get("input_material", "illustration"),
            style_target=raw.get("style_target", "chibi_anime"),
            key_features=raw.get("key_features", []),
            color_palette=raw.get("color_palette", []),
            confidence=float(raw.get("confidence", 0.0)),
            reasoning=raw.get("reasoning", raw.get("description", "")),
            raw_response=json.dumps(raw, ensure_ascii=False),
        )
