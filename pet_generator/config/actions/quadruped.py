"""四足（quadruped）动作集 — 10 个动作。

适用于四足行走的动物（猫、狗、狐狸等）。
Prompt 约束：使用 paws / legs / tail / ears，强调 "all four legs visible"，
禁止引用 arms / hands。
"""

from __future__ import annotations

from .base import ActionDef

QUADRUPED_ACTIONS: list[ActionDef] = [
    ActionDef(
        name="idle",
        description="待机：四足自然站立，尾巴轻摆",
        pose_prompt=(
            "standing on all four legs in a natural relaxed stance, tail resting, "
            "ears alert, calm expression, weight evenly distributed on all paws, "
            "all four legs visible"
        ),
        video_prompt=(
            "subtle idle motion, gentle tail swaying side to side, slight ear twitching, "
            "very subtle breathing movement in the body, calm and relaxed"
        ),
        duration_secs=3.0,
        fps=12,
        loop=True,
    ),
    ActionDef(
        name="happy",
        description="开心：兴奋蹦跳，尾巴高举",
        pose_prompt=(
            "joyful mid-jump pose with all four legs off the ground, tail raised high, "
            "ears perked forward, big happy expression, body stretched upward, "
            "all four legs visible"
        ),
        video_prompt=(
            "excited bouncing motion, hopping up and down on all four legs, "
            "tail wagging rapidly, ears bouncing, joyful playful energy"
        ),
        duration_secs=2.0,
        fps=12,
        loop=True,
    ),
    ActionDef(
        name="sleep",
        description="睡觉：蜷缩躺卧熟睡",
        pose_prompt=(
            "lying down curled up asleep, all four legs tucked under the body, "
            "tail wrapped around, eyes closed, peaceful expression, body fully at rest"
        ),
        video_prompt=(
            "very slow deep breathing while sleeping, gentle rise and fall of the body, "
            "occasional ear or paw twitch, calm and still"
        ),
        duration_secs=4.0,
        fps=8,
        loop=True,
    ),
    ActionDef(
        name="tail_wag",
        description="摇尾：尾巴快速左右摆动",
        pose_prompt=(
            "tail raised high and wagging to one side, body slightly wiggling with enthusiasm, "
            "ears perked forward, happy alert expression, standing on all four legs, "
            "all four legs visible"
        ),
        video_prompt=(
            "rapid tail wagging motion from side to side, body wiggling slightly with the "
            "tail movement, ears bouncing, excited and joyful energy"
        ),
        duration_secs=2.0,
        fps=12,
        loop=True,
    ),
    ActionDef(
        name="walk",
        description="行走：四足缓步前进",
        pose_prompt=(
            "mid-stride walking pose on all four legs, one front paw lifted forward, "
            "tail relaxed, ears alert, calm focused expression, all four legs visible"
        ),
        video_prompt=(
            "steady walking motion in place, all four legs moving in a natural gait, "
            "tail swaying gently, body bobbing slightly with each step, calm pace"
        ),
        duration_secs=2.0,
        fps=12,
        loop=True,
    ),
    ActionDef(
        name="run",
        description="奔跑：四足快速奔跑",
        pose_prompt=(
            "full sprint pose with body stretched out, all four legs extended mid-gallop, "
            "tail streaming behind, ears pinned back, determined expression, "
            "all four legs visible"
        ),
        video_prompt=(
            "fast running motion in place, legs galloping rapidly, body stretching and "
            "contracting with each stride, tail flowing, energetic and quick"
        ),
        duration_secs=1.5,
        fps=12,
        loop=True,
    ),
    ActionDef(
        name="sit",
        description="坐下：后腿蹲坐，前腿直立",
        pose_prompt=(
            "sitting pose on hind legs, front legs straight and planted, tail curled around "
            "the side, ears alert, attentive calm expression, all four legs visible"
        ),
        video_prompt=(
            "settling into a sit, hind legs folding down, front legs planting firmly, "
            "tail curling around, then holding a calm seated posture"
        ),
        duration_secs=2.0,
        fps=12,
        loop=False,
    ),
    ActionDef(
        name="pounce",
        description="扑击：蓄力后向前扑跃",
        pose_prompt=(
            "mid-pounce pose, body lunging forward, front paws extended ahead, "
            "hind legs pushing off, tail straight back, focused intense expression, "
            "all four legs visible"
        ),
        video_prompt=(
            "quick pouncing motion, crouching low then leaping forward, front paws reaching "
            "out, landing softly, explosive playful attack"
        ),
        duration_secs=1.5,
        fps=12,
        loop=False,
    ),
    ActionDef(
        name="tilt_head",
        description="歪头：好奇地歪头观察",
        pose_prompt=(
            "curious head tilt pose, head tilted to one side, ears perked forward, "
            "standing on all four legs, tail relaxed, attentive inquisitive expression, "
            "all four legs visible"
        ),
        video_prompt=(
            "curious head tilting motion, head tilting to one side then the other, "
            "ears rotating forward, body staying still, inquisitive and alert"
        ),
        duration_secs=2.0,
        fps=12,
        loop=False,
    ),
    ActionDef(
        name="scratch",
        description="挠痒：用后腿挠耳朵",
        pose_prompt=(
            "scratching pose, sitting with one hind leg raised up scratching behind the ear, "
            "head tilted toward the leg, tail resting, content expression, all four legs visible"
        ),
        video_prompt=(
            "scratching motion, hind leg rapidly scratching behind the ear, "
            "head bobbing with the scratch, body shaking slightly, relieved and content"
        ),
        duration_secs=2.0,
        fps=12,
        loop=False,
    ),
]
