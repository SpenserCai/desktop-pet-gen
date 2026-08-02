"""Prompt 模板库。

聚合各阶段的 prompt 组装入口，供 pipeline 各 stage 调用：
- 分类：``classify``（CLASSIFY_SYSTEM_PROMPT / build_classify_user_prompt）
- 标准化：``standardize.get_standardize_prompt``
- 姿态：``pose.get_pose_prompt``
- 视频：``video.get_video_prompt``
"""

from __future__ import annotations

from .classify import (
    BODY_TYPES,
    CLASSIFY_SYSTEM_PROMPT,
    CLASSIFY_USER_PROMPT,
    INPUT_MATERIALS,
    STYLE_TARGETS,
    build_classify_user_prompt,
)
from .pose import get_pose_prompt
from .standardize import get_standardize_prompt
from .video import VIDEO_COMMON_CONSTRAINTS, get_video_prompt

__all__ = [
    # classify
    "CLASSIFY_SYSTEM_PROMPT",
    "CLASSIFY_USER_PROMPT",
    "build_classify_user_prompt",
    "BODY_TYPES",
    "INPUT_MATERIALS",
    "STYLE_TARGETS",
    # standardize
    "get_standardize_prompt",
    # pose
    "get_pose_prompt",
    # video
    "get_video_prompt",
    "VIDEO_COMMON_CONSTRAINTS",
]
