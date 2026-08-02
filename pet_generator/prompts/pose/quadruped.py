"""四足（quadruped）姿态通用约束。"""

from __future__ import annotations

POSE_CONSTRAINTS = """\
Render the animal performing the following pose.

ACTION POSE:
{action_pose_prompt}

GENERAL CONSTRAINTS (quadruped):
- Four-legged animal, all four legs clearly visible and anatomically consistent
- Use paws / legs / tail / ears terminology; do NOT add arms or hands
- Side-profile or three-quarter view that keeps all four legs readable
- Tail and ears consistent with the described emotion/action
- Centered in frame, full body occupying about 70% of the image width
- Pure white background (#FFFFFF), clean, no background elements
- Even flat lighting, consistent character design
"""
