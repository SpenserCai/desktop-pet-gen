"""Stage 1: 分类感知标准化 — 将输入图片转换为统一风格的标准参考图。

根据 Stage 0 的分类结果（body_type / input_material / style_target），
选择对应的标准化 prompt，调用图像编辑 Provider 生成标准参考图。

标准图是后续所有姿态生成与视频生成的"基准帧"，必须保证：
- 风格统一（由 style_target 驱动）
- 材质转换（如手办照片 → 数字插画）
- 关键特征保留（key_features）

错误处理:
- 生成失败 → 抛出 RuntimeError（管线终止），因为标准图是后续所有阶段的前置依赖。
"""

from __future__ import annotations

import logging
from pathlib import Path

from pet_generator.prompts import get_standardize_prompt
from pet_generator.providers.base import ImageGenProvider

from .classifier import ClassificationResult

logger = logging.getLogger(__name__)


class Standardizer:
    """Stage 1 — 分类感知标准化。

    Args:
        image_provider: 图像生成/编辑 Provider（已初始化）。
    """

    def __init__(self, image_provider: ImageGenProvider) -> None:
        self._image_provider = image_provider

    def run(
        self,
        input_image: Path,
        classification: ClassificationResult,
        output_dir: Path,
    ) -> Path:
        """执行标准化，生成标准参考图。

        Args:
            input_image: 原始输入图片路径。
            classification: Stage 0 的分类结果。
            output_dir: 输出目录（不存在时自动创建）。

        Returns:
            生成的标准图路径。

        Raises:
            RuntimeError: 图像生成失败（管线不可继续）。
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # 1. 根据分类结果组装标准化 prompt
        prompt = get_standardize_prompt(
            body_type=classification.body_type,
            input_material=classification.input_material,
            style_target=classification.style_target,
            key_features=classification.key_features,
        )
        logger.info(
            "标准化 prompt 已生成 (body_type=%s, material=%s, style=%s)",
            classification.body_type,
            classification.input_material,
            classification.style_target,
        )

        # 2. 调用图像编辑 Provider
        result = self._image_provider.edit(
            image_paths=[input_image],
            prompt=prompt,
            output_dir=output_dir,
        )

        # 3. 校验结果
        if not result.success or result.first_path is None:
            error_msg = result.error or "未知错误（无输出文件）"
            raise RuntimeError(
                f"标准化失败（管线终止）: {error_msg}。"
                f"输入: {input_image}, metadata: {result.metadata}"
            )

        standard_path = result.first_path
        logger.info("标准图已生成: %s", standard_path)
        return standard_path
