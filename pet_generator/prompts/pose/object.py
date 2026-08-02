"""物品（object）姿态通用约束。"""

from __future__ import annotations

POSE_CONSTRAINTS = """\
Render the object performing the following pose.

ACTION POSE:
{action_pose_prompt}

GENERAL CONSTRAINTS (object):
- Anthropomorphized object; convey motion via micro-movement, glow and physical sway
- Use object / item / surface terminology; do NOT add real limbs
- Preserve the object's core recognizable shape and silhouette
- Optional cute minimal face (small dot eyes) if the action implies emotion
- Front-facing product view, centered, occupying about 70% of the image height
- Pure white background (#FFFFFF), clean, no background elements
- Even flat lighting, consistent character design
"""
