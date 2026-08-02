"""视频（video）Prompt 组装。

``get_video_prompt`` 将某个动作的 ``video_prompt`` 包装上通用视频约束，
生成可直接交给视频生成模型的完整 prompt。
"""

from __future__ import annotations

__all__ = ["get_video_prompt", "VIDEO_COMMON_CONSTRAINTS"]

# 所有视频共享的通用约束
VIDEO_COMMON_CONSTRAINTS = (
    "smooth animation, consistent character design, white/clean background, "
    "no camera movement, loop-friendly"
)


def get_video_prompt(action_video_prompt: str, loop: bool = True) -> str:
    """包装视频 prompt，添加通用视频约束。

    Args:
        action_video_prompt: 来自 ``ActionDef.video_prompt`` 的运动描述。
        loop: 是否循环；为 True 时强调首尾帧衔接以便无缝循环。

    Returns:
        完整的视频生成 prompt。
    """
    motion = action_video_prompt.strip()
    loop_hint = (
        "The first and last frames should match closely for a seamless loop."
        if loop
        else "This is a one-shot motion that starts and ends at a natural resting state."
    )
    return (
        f"MOTION DESCRIPTION:\n{motion}\n\n"
        f"GENERAL VIDEO CONSTRAINTS:\n{VIDEO_COMMON_CONSTRAINTS}\n\n"
        f"LOOP HANDLING:\n{loop_hint}"
    )
