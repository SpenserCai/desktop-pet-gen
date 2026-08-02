"""分类器领域配置 — 体型定义、分类规则与输出 Schema。

将分类器的领域知识（体型定义、材质类型、风格目标）与通用 Settings 解耦，
便于独立演进和测试。

Usage:
    from pet_generator.config.classifier_config import ClassifierConfig

    cfg = ClassifierConfig()
    system_prompt = cfg.system_prompt
    user_prompt = cfg.user_prompt
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# 体型分类定义（与 config/actions/ 注册表严格对齐）
# ---------------------------------------------------------------------------

VALID_BODY_TYPES = ["humanoid", "quadruped", "limbless", "object"]
VALID_INPUT_MATERIALS = ["photo_real", "photo_figure", "pixel_art", "illustration", "3d_render"]
VALID_STYLE_TARGETS = ["chibi_anime", "flat_cartoon", "pixel", "clay", "keep_original"]
VALID_SUBJECT_CATEGORIES = ["living", "non_living"]


@dataclass
class ClassifierConfig:
    """分类器领域配置 — 提示词模板与输出格式。

    与 ClassifierSettings（连接参数）互补：
    - ClassifierSettings: model, api_base, temperature 等运行时参数
    - ClassifierConfig: 提示词、分类规则、输出 Schema 等领域知识
    """

    confidence_threshold: float = 0.7
    max_retries: int = 2

    # 默认降级值（全部重试失败后使用）
    fallback_body_type: str = "humanoid"
    fallback_input_material: str = "illustration"
    fallback_style_target: str = "chibi_anime"

    @property
    def system_prompt(self) -> str:
        """分类器 system prompt。"""
        return (
            "你是一个图像分析专家，专门用于桌面宠物生成管线的输入分类。\n"
            "分析用户提供的图片，输出严格的JSON格式分类结果。"
        )

    @property
    def user_prompt(self) -> str:
        """分类器 user prompt — 定义输出 JSON Schema 和分类规则。"""
        return """\
分析这张图片，输出以下JSON（不要输出其他内容）：
{
  "subject_category": "living 或 non_living（是否为生物/活物，包括人、动物、任何有生命的角色）",
  "body_type": "humanoid（双足直立有手臂）| quadruped（四足行走）| limbless（无明显肢体如史莱姆/幽灵）| object（非生物物品）",
  "input_material": "photo_real（真人/真实动物照片）| photo_figure（手办/模型/黏土照片）| pixel_art（像素画）| illustration（插画/已有卡通）| 3d_render（3D渲染图）",
  "style_target": "chibi_anime（Q版动漫）| flat_cartoon（扁平卡通）| pixel（像素风）| clay（黏土风）| keep_original（保持原风格）",
  "key_features": ["角色的3-5个最关键视觉特征"],
  "color_palette": ["2-4个主色调hex值"],
  "confidence": 0.95,
  "reasoning": "一句话说明分类理由"
}

分类规则：
- 人/拟人化动物（双足直立有手）→ humanoid
- 猫/狗/马等四足行走动物 → quadruped
- 史莱姆/幽灵/水滴/果冻等无肢体 → limbless
- 杯子/剑/机器人/食物等非生物 → object
- 手办/模型照片即使拍的是动漫角色，input_material 也是 photo_figure
- 默认 style_target 为 chibi_anime（除非输入已是像素画或插画）"""

    def validate_result(self, result: dict) -> tuple[bool, str]:
        """校验分类器输出是否合法。

        Returns:
            (is_valid, error_message)
        """
        if "body_type" not in result:
            return False, "Missing 'body_type' field"
        if result["body_type"] not in VALID_BODY_TYPES:
            return False, (
                f"Invalid body_type '{result['body_type']}'. Must be one of: {VALID_BODY_TYPES}"
            )
        if "input_material" in result and result["input_material"] not in VALID_INPUT_MATERIALS:
            return False, (
                f"Invalid input_material '{result['input_material']}'. "
                f"Must be one of: {VALID_INPUT_MATERIALS}"
            )
        confidence = result.get("confidence", 0)
        if not isinstance(confidence, (int, float)) or not (0 <= confidence <= 1):
            return False, f"Invalid confidence value: {confidence}"
        return True, ""

    def is_confident(self, result: dict) -> bool:
        """判断分类结果是否达到置信阈值。"""
        return result.get("confidence", 0) >= self.confidence_threshold
