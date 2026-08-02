"""物品（object）动作集 — 9 个动作。

适用于拟人化的日常物品（杯子、盆栽、家电、食物等）。
Prompt 约束：使用 object / item / surface，动画以微动 / 光效 / 物理摇摆为主，
可选萌化面部（small dot eyes）。不引用真实肢体词汇。
"""

from __future__ import annotations

from .base import ActionDef

OBJECT_ACTIONS: list[ActionDef] = [
    ActionDef(
        name="idle",
        description="待机：轻微悬浮，柔和光晕",
        pose_prompt=(
            "stationary object with very subtle floating motion, gentle up-down hover, "
            "soft shadow beneath, cute minimal face (small dot eyes) if applicable"
        ),
        video_prompt=(
            "very subtle hovering motion, gentle up and down float, slight rotation wobble, "
            "soft ambient glow pulsing, peaceful and still"
        ),
        duration_secs=3.0,
        fps=8,
        loop=True,
    ),
    ActionDef(
        name="happy",
        description="开心：欢快弹跳，光效闪烁",
        pose_prompt=(
            "object mid-bounce slightly elevated, cheerful expression (small dot eyes, smile) "
            "if applicable, soft glow around the surface, joyful energy"
        ),
        video_prompt=(
            "happy bouncing motion, object bobbing up and down cheerfully, soft glow pulsing, "
            "tiny sparkles around the surface, joyful and lively"
        ),
        duration_secs=2.0,
        fps=12,
        loop=True,
    ),
    ActionDef(
        name="sleep",
        description="睡觉：静止微光，缓慢起伏",
        pose_prompt=(
            "object resting still, dimmed soft glow, closed-eye expression (if has face), "
            "calm peaceful surface, soft shadow beneath, completely at rest"
        ),
        video_prompt=(
            "very slow subtle pulsing glow, gentle barely-there rise and fall, "
            "dim ambient light breathing, calm and sleepy, almost still"
        ),
        duration_secs=4.0,
        fps=8,
        loop=True,
    ),
    ActionDef(
        name="wobble",
        description="摇晃：物理摇摆后回正",
        pose_prompt=(
            "object tilted slightly to one side mid-wobble, soft shadow shifting, "
            "playful expression (if has face), stable rounded base"
        ),
        video_prompt=(
            "physical wobbling motion, object rocking side to side like a roly-poly toy, "
            "swaying then settling back to center, playful rhythmic rocking"
        ),
        duration_secs=2.0,
        fps=12,
        loop=True,
    ),
    ActionDef(
        name="glow",
        description="发光：光晕由弱到强脉动",
        pose_prompt=(
            "object glowing softly, bright ambient halo around the surface, "
            "content expression (if has face), warm luminous aura"
        ),
        video_prompt=(
            "glowing pulsation, ambient halo brightening and dimming rhythmically, "
            "soft light radiating from the surface, warm gentle glow cycle"
        ),
        duration_secs=2.5,
        fps=12,
        loop=True,
    ),
    ActionDef(
        name="shake",
        description="抖动：快速左右抖动",
        pose_prompt=(
            "object mid-shake slightly blurred, vibrating to one side, "
            "surprised expression (if has face), motion lines around the surface"
        ),
        video_prompt=(
            "rapid shaking motion, object vibrating quickly side to side, "
            "small jittery movement, surprised energy then settling still"
        ),
        duration_secs=1.5,
        fps=12,
        loop=False,
    ),
    ActionDef(
        name="tilt",
        description="倾斜：好奇地侧倾",
        pose_prompt=(
            "object tilted to one side curiously, soft shadow shifting, "
            "inquisitive expression (if has face), balanced on its base"
        ),
        video_prompt=(
            "curious tilting motion, object leaning to one side then the other, "
            "gentle rocking tilt, inquisitive and playful, then returning to center"
        ),
        duration_secs=2.0,
        fps=12,
        loop=False,
    ),
    ActionDef(
        name="bounce_small",
        description="小跳：轻微上下弹跳",
        pose_prompt=(
            "object slightly elevated mid-small-bounce, soft squash on the base, "
            "cheerful expression (if has face), small shadow beneath"
        ),
        video_prompt=(
            "small bouncy motion, object hopping gently up and down, slight squash and "
            "stretch on the surface, soft shadow shrinking and growing, playful and light"
        ),
        duration_secs=1.5,
        fps=12,
        loop=True,
    ),
    ActionDef(
        name="sparkle",
        description="闪光：表面星光闪烁",
        pose_prompt=(
            "object sparkling, small star glints on the surface, delighted expression "
            "(if has face), bright clean highlights, magical shine"
        ),
        video_prompt=(
            "sparkling motion, small star glints twinkling across the surface in sequence, "
            "bright highlights flashing, magical shimmer then fading, delightful"
        ),
        duration_secs=2.0,
        fps=12,
        loop=False,
    ),
]
