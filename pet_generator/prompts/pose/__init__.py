"""姿态（pose）Prompt 组装。

``get_pose_prompt`` 将某个动作的 ``pose_prompt`` 用对应 body_type 的通用约束包装，
生成可直接交给图像生成模型的完整尾帧 prompt。
"""

from __future__ import annotations

from . import humanoid, limbless, object, quadruped

__all__ = ["get_pose_prompt"]

# body_type -> 通用约束模板（含 {action_pose_prompt} 占位）
_POSE_CONSTRAINTS: dict[str, str] = {
    "humanoid": humanoid.POSE_CONSTRAINTS,
    "quadruped": quadruped.POSE_CONSTRAINTS,
    "limbless": limbless.POSE_CONSTRAINTS,
    "object": object.POSE_CONSTRAINTS,
}


def get_pose_prompt(body_type: str, action_pose_prompt: str) -> str:
    """包装动作 pose_prompt，添加该 body_type 的通用约束。

    Args:
        body_type: 体型（humanoid/quadruped/limbless/object）。
        action_pose_prompt: 来自 ``ActionDef.pose_prompt`` 的动作姿态描述。

    Returns:
        完整的尾帧生成 prompt。

    Raises:
        ValueError: body_type 非法。
    """
    if body_type not in _POSE_CONSTRAINTS:
        raise ValueError(
            f"Unknown body_type: {body_type}. Available: {list(_POSE_CONSTRAINTS.keys())}"
        )
    return _POSE_CONSTRAINTS[body_type].format(action_pose_prompt=action_pose_prompt.strip())
