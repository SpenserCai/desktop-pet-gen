"""人形（humanoid）标准化模板。

核心要求：A-pose 正面直立，双臂自然下垂约 30°，睁眼中性表情，
居中占画面高度 80%，纯白背景。
"""

from __future__ import annotations

# 该 body_type 的姿态/构图标准化指令（英文，供图像生成模型消费）
STANDARDIZE_TEMPLATE = """\
Character standardization reference sheet for a HUMANOID (bipedal) character.

POSE REQUIREMENTS:
- Front-facing upright standing pose in a clean A-pose
- Both arms hanging naturally at the sides, angled roughly 30 degrees away from the body
- Legs straight, slightly apart, weight evenly distributed
- Eyes open, neutral calm facial expression
- Symmetrical, balanced posture facing directly toward the viewer

COMPOSITION REQUIREMENTS:
- Character centered in the frame
- Full body visible, occupying about 80% of the image height
- Generous even margin on all sides
- Pure white background (#FFFFFF), completely clean, no shadows on the background
- Even flat lighting, no dramatic shadows or highlights

IDENTITY PRESERVATION:
- Keep the exact same character identity: hairstyle, hair color, clothing,
  accessories, color palette and body proportions
- Only adjust the pose and background; do not redesign the character
"""
