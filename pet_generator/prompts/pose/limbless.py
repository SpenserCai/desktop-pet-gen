"""无肢体（limbless）姿态通用约束。"""

from __future__ import annotations

POSE_CONSTRAINTS = """\
Render the character performing the following pose.

ACTION POSE:
{action_pose_prompt}

GENERAL CONSTRAINTS (limbless):
- Amorphous/blob character with NO limbs; animate via body shape only
- Use body / shape / form terminology; do NOT add arms, legs, hands, paws or tail
- Apply squash & stretch principles to convey the motion/pose
- Clean well-defined silhouette, front-facing and centered
- Occupying about 70% of the image height
- Pure white background (#FFFFFF), clean, no background elements
- Even flat lighting, consistent character design
"""
