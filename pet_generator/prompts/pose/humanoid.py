"""人形（humanoid）姿态通用约束。"""

from __future__ import annotations

# 包装任意动作 pose_prompt 的通用约束（英文）
POSE_CONSTRAINTS = """\
Render the character performing the following pose.

ACTION POSE:
{action_pose_prompt}

GENERAL CONSTRAINTS (humanoid):
- Bipedal character standing upright, front-facing toward the viewer
- Clear readable silhouette of the full body, head to feet visible
- Arms and legs anatomically consistent with the described pose
- Neutral expression unless the action specifies otherwise
- Centered in frame, full body occupying about 80% of the image height
- Pure white background (#FFFFFF), clean, no background elements
- Even flat lighting, consistent character design
"""
