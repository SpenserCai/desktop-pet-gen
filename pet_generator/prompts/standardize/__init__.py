"""标准化（standardize）Prompt 组装。

将三个正交维度组装成一条完整的图像生成 prompt：
1. 目标风格指令（STYLE_INSTRUCTIONS）
2. 材质转换指令（MATERIAL_INSTRUCTIONS）— 部分含 ``{style_target}`` 占位
3. body_type 专属的姿态/构图模板（各 body_type 模块的 STANDARDIZE_TEMPLATE）
4. 关键特征保留清单（key_features）

设计取舍：
- 三个维度解耦为独立字典/模块，便于单独测试与扩展。
- ``{style_target}`` 占位用风格**描述文本**填充，而非枚举名，
  使生成模型获得可执行的风格语义。
"""

from __future__ import annotations

from . import humanoid, limbless, object, quadruped

__all__ = [
    "EXPRESSION_RESET_BLOCK",
    "MATERIAL_INSTRUCTIONS",
    "STYLE_INSTRUCTIONS",
    "get_standardize_prompt",
]

# body_type -> 标准化模板模块
_BODY_TEMPLATES: dict[str, str] = {
    "humanoid": humanoid.STANDARDIZE_TEMPLATE,
    "quadruped": quadruped.STANDARDIZE_TEMPLATE,
    "limbless": limbless.STANDARDIZE_TEMPLATE,
    "object": object.STANDARDIZE_TEMPLATE,
}


# 材质转换指令：部分模板含 {style_target} 占位符，由风格描述文本填充
MATERIAL_INSTRUCTIONS: dict[str, str] = {
    "photo_figure": (
        "CRITICAL MATERIAL CONVERSION: This is a photograph of a physical figurine/model. "
        "You MUST remove ALL physical material properties: plastic sheen, resin texture, "
        "paint-like surface, mold lines, base/stand. The output must look like a LIVING "
        "character, NOT a toy or collectible figure. Convert to clean digital art style."
    ),
    "photo_real": (
        "STYLE CONVERSION: This is a real photograph. Convert to {style_target} style. "
        "Simplify realistic details into clean stylized aesthetics. Maintain identity: "
        "same hairstyle, hair color, clothing, accessories, body proportions."
    ),
    "pixel_art": (
        "STYLE PRESERVATION: This is pixel art. Maintain the pixel art style exactly. "
        "Only clean up artifacts and adjust pose/background. Do NOT convert to "
        "smooth/realistic/vector style."
    ),
    "illustration": (
        "STYLE PRESERVATION: This is already an illustration/cartoon. Maintain the existing "
        "art style. Only adjust pose and background. Minimal style changes — preserve the "
        "artist's original aesthetic."
    ),
    "3d_render": (
        "STYLE CONVERSION: This is a 3D render. Re-render in {style_target} style. "
        "Remove 3D-specific artifacts: complex lighting, reflections, depth of field. "
        "Convert to flat/clean 2D appearance while maintaining the character design."
    ),
}


# 目标风格指令：作为 {style_target} 占位的填充文本，也单独作为风格段落
STYLE_INSTRUCTIONS: dict[str, str] = {
    "chibi_anime": (
        "chibi anime style, 2.5-3 head-to-body ratio, large expressive eyes, "
        "clean lineart, vibrant flat colors"
    ),
    "flat_cartoon": ("flat cartoon style, bold outlines, simple shapes, minimal shading"),
    "pixel": ("pixel art style, limited color palette, crisp pixels, retro game aesthetic"),
    "clay": ("clay/plasticine style, soft rounded forms, matte surface, handcrafted look"),
    "keep_original": ("maintain the original art style exactly"),
}


# 表情与姿态重置块（英文，供图像生成模型消费）。
#
# 设计目的：
# - 各 body 模板里的表情指令权重过低（如 humanoid 仅一句 "Eyes open, neutral calm
#   facial expression"），且模板反复强调 "Keep the exact same character identity ...
#   do not redesign the character"，模型可能把【表情/姿态】也当作 identity 保留，
#   从而抵消表情指令，导致标准参考图保留输入图的闭眼/夸张表情。
# - 该块以最高优先级显式声明：表情与姿态【不属于】需要保留的 identity，必须重置为
#   睁眼 + 自然中性表情 + 干净自然的静止姿态；需要保留的 identity 仅限外观特征。
#
# 通用性：使用 "if the character has eyes/a face" 兼容 limbless/object 无脸情形。
# 安全性：本块为直接字符串拼接（不参与 .format），且全文不含任何裸花括号，避免误伤。
# 体态兼容：默认要求对称、面向观众；但精确的体态朝向以各 body 模板的 POSE REQUIREMENTS
# 为准（例如 quadruped 为侧面），本块仅强制表情重置与 identity 边界，不覆盖体态细节。
EXPRESSION_RESET_BLOCK = """\
CRITICAL — EXPRESSION & POSE RESET (highest priority):
This block overrides any conflicting instruction below, including any
"keep the same identity" or "do not redesign the character" instruction.

MANDATORY RESET (apply to every character, regardless of body type):
- Eyes OPEN and clearly visible, if the character has eyes. Never closed,
  never squinting, never winking.
- A natural, neutral, calm facial expression, if the character has a face.
  No exaggerated, goofy, surprised, angry, crying or laughing expression.
- A relaxed, natural, completely stationary standing or resting pose. The
  character is still and at rest, not mid-action and not gesturing.
- Symmetrical, balanced and facing the viewer by default, unless the
  body-type POSE REQUIREMENTS section below defines a different canonical
  orientation (for example a side profile); in that case follow that
  canonical orientation while STILL applying the open-eyes and
  neutral-expression reset above.

EXPRESSION AND POSE ARE NOT IDENTITY:
- Facial expression and body pose are NOT part of the character identity
  that must be preserved.
- Even if the input image shows a different expression (closed eyes,
  exaggerated, goofy, etc.) or a different pose, you MUST reset it to:
  open eyes (if the character has eyes), a natural neutral expression,
  and a clean natural stationary pose.
- The identity that MUST be preserved is limited to appearance features
  only: hairstyle and hair color, clothing, accessories, color palette,
  body proportions, and texture or material details.
"""


def get_standardize_prompt(
    body_type: str,
    input_material: str,
    style_target: str,
    key_features: list[str],
) -> str:
    """组装完整的标准化 prompt。

    Args:
        body_type: 体型（humanoid/quadruped/limbless/object）。
        input_material: 输入材质（见 MATERIAL_INSTRUCTIONS）。
        style_target: 目标风格（见 STYLE_INSTRUCTIONS）。
        key_features: 需要保留的关键视觉特征列表。

    Returns:
        完整的标准化 prompt 字符串。

    Raises:
        ValueError: 任一枚举值非法。
    """
    if body_type not in _BODY_TEMPLATES:
        raise ValueError(
            f"Unknown body_type: {body_type}. Available: {list(_BODY_TEMPLATES.keys())}"
        )
    if input_material not in MATERIAL_INSTRUCTIONS:
        raise ValueError(
            f"Unknown input_material: {input_material}. "
            f"Available: {list(MATERIAL_INSTRUCTIONS.keys())}"
        )
    if style_target not in STYLE_INSTRUCTIONS:
        raise ValueError(
            f"Unknown style_target: {style_target}. Available: {list(STYLE_INSTRUCTIONS.keys())}"
        )

    style_text = STYLE_INSTRUCTIONS[style_target]
    # 材质指令中的 {style_target} 占位用风格描述文本填充
    material_text = MATERIAL_INSTRUCTIONS[input_material].format(style_target=style_text)
    body_template = _BODY_TEMPLATES[body_type]

    if key_features:
        features_block = "KEY FEATURES TO PRESERVE:\n" + "\n".join(
            f"- {feature}" for feature in key_features
        )
    else:
        features_block = "KEY FEATURES TO PRESERVE:\n- (none specified; preserve overall identity)"

    return f"""\
{EXPRESSION_RESET_BLOCK}

TARGET STYLE:
{style_text}

MATERIAL HANDLING:
{material_text}

{body_template}
{features_block}
"""
