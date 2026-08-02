"""无肢体（limbless）动作集 — 9 个动作。

适用于史莱姆、水滴、幽灵、团子等无四肢的形体角色。
Prompt 约束：使用 body / shape / form，核心动画原理为 squash & stretch，
禁止引用任何肢体词汇（arms / legs / hands / paws / tail 等）。
"""

from __future__ import annotations

from .base import ActionDef

LIMBLESS_ACTIONS: list[ActionDef] = [
    ActionDef(
        name="idle",
        description="待机：自然团状静止，轻微脉动",
        pose_prompt=(
            "resting in natural blob shape, slightly rounded, calm expression (if has face), "
            "subtle surface tension visible, completely still"
        ),
        video_prompt=(
            "gentle breathing-like pulsation, body slowly expanding and contracting, "
            "very subtle wobble, jelly-like surface movement, calm and peaceful"
        ),
        duration_secs=3.0,
        fps=12,
        loop=True,
    ),
    ActionDef(
        name="happy",
        description="开心：兴奋上下弹跳变形",
        pose_prompt=(
            "joyful squashed-flat shape mid-celebration, body widened and compressed, "
            "big happy expression (if has face), surface rippling with excitement"
        ),
        video_prompt=(
            "excited bouncing and jiggling, body squashing and stretching rapidly, "
            "jelly-like wobble, joyful energetic pulsation, happy vibration"
        ),
        duration_secs=1.5,
        fps=12,
        loop=True,
    ),
    ActionDef(
        name="sleep",
        description="睡觉：瘫软静止，缓慢起伏",
        pose_prompt=(
            "settled flat resting shape, body spread out and relaxed, eyes closed (if has face), "
            "peaceful expression, soft rounded edges, completely at rest"
        ),
        video_prompt=(
            "very slow deep breathing pulsation, body gently rising and falling, "
            "soft surface ripples, calm and completely relaxed, sleepy rhythm"
        ),
        duration_secs=4.0,
        fps=8,
        loop=True,
    ),
    ActionDef(
        name="bounce",
        description="弹跳：squash & stretch 上下弹跳",
        pose_prompt=(
            "mid-bounce stretched vertically, body elongated upward, slightly narrower than "
            "resting state, excited expression (if has face)"
        ),
        video_prompt=(
            "bouncy jumping motion, squash and stretch principle: flattening on landing then "
            "stretching upward on bounce, rhythmic and playful, jelly-like deformation"
        ),
        duration_secs=2.0,
        fps=12,
        loop=True,
    ),
    ActionDef(
        name="squish",
        description="压扁：被压扁后回弹",
        pose_prompt=(
            "fully squashed flat shape, body compressed wide and low, squeezed expression "
            "(if has face), edges bulging outward from pressure"
        ),
        video_prompt=(
            "squishing motion, body compressing flat then springing back to shape, "
            "squash and stretch rebound, jelly-like wobble on recovery, playful"
        ),
        duration_secs=1.5,
        fps=12,
        loop=False,
    ),
    ActionDef(
        name="stretch_vertical",
        description="拉伸：向上拉长身体",
        pose_prompt=(
            "stretched tall vertically, body elongated upward, narrower than resting state, "
            "top slightly rounded, reaching upward expression (if has face)"
        ),
        video_prompt=(
            "stretching upward motion, body elongating vertically then relaxing back, "
            "squash and stretch, smooth jelly-like extension and rebound"
        ),
        duration_secs=2.0,
        fps=12,
        loop=False,
    ),
    ActionDef(
        name="float",
        description="漂浮：轻盈上下飘浮",
        pose_prompt=(
            "floating gently in the air, body slightly off the ground, soft rounded shape, "
            "calm dreamy expression (if has face), subtle glow beneath"
        ),
        video_prompt=(
            "gentle floating motion, body drifting slowly up and down, soft bobbing, "
            "slight surface wobble, weightless and dreamy, calm hovering"
        ),
        duration_secs=3.0,
        fps=8,
        loop=True,
    ),
    ActionDef(
        name="spin",
        description="旋转：原地快速旋转",
        pose_prompt=(
            "mid-spin shape, body slightly distorted from rotation, surface swirling, "
            "dizzy playful expression (if has face), motion blur at edges"
        ),
        video_prompt=(
            "spinning motion in place, body rotating rapidly, surface swirling around, "
            "slight wobble, playful dizzy spin then settling"
        ),
        duration_secs=2.0,
        fps=12,
        loop=False,
    ),
    ActionDef(
        name="wobble",
        description="摇晃：果冻般左右摇晃",
        pose_prompt=(
            "mid-wobble shape leaning to one side, body tilted with jelly-like deformation, "
            "playful expression (if has face), soft unstable edges"
        ),
        video_prompt=(
            "wobbling motion side to side, body swaying like jelly, squashing and stretching "
            "with each wobble, playful unstable bounce, rhythmic jiggle"
        ),
        duration_secs=2.5,
        fps=12,
        loop=True,
    ),
]
