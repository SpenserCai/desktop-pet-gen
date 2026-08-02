"""分类阶段 Prompt 模板。

分类器（vision LLM）一次性输出三个维度的判断：
- ``body_type``：体型（决定动作集与标准化/姿态模板）
- ``input_material``：输入素材材质（决定材质转换指令）
- ``style_target``：目标风格（决定风格化指令）

输出为严格 JSON，便于下游程序化消费。
"""

from __future__ import annotations

# 合法取值常量（供校验与文档对齐）
BODY_TYPES: list[str] = ["humanoid", "quadruped", "limbless", "object"]
INPUT_MATERIALS: list[str] = [
    "photo_figure",
    "photo_real",
    "pixel_art",
    "illustration",
    "3d_render",
]
STYLE_TARGETS: list[str] = [
    "chibi_anime",
    "flat_cartoon",
    "pixel",
    "clay",
    "keep_original",
]


CLASSIFY_SYSTEM_PROMPT = """\
你是一个图像分析专家，专精于角色/宠物图像的结构化分类。你的任务是分析用户提供的
图片，从三个维度进行判断，并以严格 JSON 格式输出结果。

## 维度 1: body_type（体型）
判断角色的身体结构，必须是以下之一：
- "humanoid": 人形/双足直立，有明确的手臂与腿（人、拟人角色、机器人、企鹅等直立角色）
- "quadruped": 四足动物，用四条腿站立行走（猫、狗、狐狸、鹿、马等）
- "limbless": 无肢体形体，没有四肢，靠形变/漂浮运动（史莱姆、水滴、幽灵、团子、蛇形等）
- "object": 拟人化日常物品，本体是物件（杯子、盆栽、家电、食物、玩具等）

## 维度 2: input_material（输入素材材质）
判断输入图片的来源/材质类型，必须是以下之一：
- "photo_figure": 实物手办/模型的照片（有塑料/树脂光泽、涂装表面、底座）
- "photo_real": 真实照片（真实人物/动物/场景的摄影照片）
- "pixel_art": 像素画（明显的像素颗粒、有限调色板）
- "illustration": 插画/卡通（已是手绘/矢量/赛璐璐风格的二维图）
- "3d_render": 3D 渲染图（复杂光照、反射、景深等 3D 特征）

## 维度 3: style_target（目标风格）
根据输入素材推荐最合适的目标风格，必须是以下之一：
- "chibi_anime": Q 版动漫风（2.5-3 头身、大眼睛、干净线稿）
- "flat_cartoon": 扁平卡通风（粗描边、简单形状、弱阴影）
- "pixel": 像素风（有限调色板、复古游戏感）
- "clay": 黏土/橡皮泥风（柔和圆润、哑光、手作感）
- "keep_original": 保持原风格（当输入已是理想风格时）

## 输出要求
仅输出一个 JSON 对象，不要输出任何额外文字或 Markdown 代码块标记，字段如下：
{
  "body_type": "<humanoid|quadruped|limbless|object>",
  "input_material": "<photo_figure|photo_real|pixel_art|illustration|3d_render>",
  "style_target": "<chibi_anime|flat_cartoon|pixel|clay|keep_original>",
  "confidence": <0.0-1.0 的整体置信度>,
  "description": "<对角色的简短中文描述，一句话>",
  "key_features": ["<影响判断的关键视觉特征>", "..."]
}
"""


CLASSIFY_USER_PROMPT = """\
请分析这张图片，输出以下 JSON：
1. body_type（体型）
2. input_material（输入素材材质）
3. style_target（推荐目标风格）
4. confidence（置信度）
5. description（角色简短描述）
6. key_features（关键视觉特征列表）

{extra_context}

仅输出 JSON，不要输出其他内容。
"""


def build_classify_user_prompt(extra_context: str = "") -> str:
    """构建分类 user prompt。

    Args:
        extra_context: 可选的补充上下文（如用户描述）；为空时占位行会被清理。
    """
    context = extra_context.strip()
    if not context:
        context = "（无补充信息）"
    return CLASSIFY_USER_PROMPT.format(extra_context=f"补充信息: {context}")
