"""人形（humanoid）动作集 — 10 个动作。

适用于双足直立、有手臂的角色（人、拟人化角色、机器人等）。
Prompt 可自由使用 arms / hands / legs / head 等肢体词汇。
"""

from __future__ import annotations

from .base import ActionDef

HUMANOID_ACTIONS: list[ActionDef] = [
    ActionDef(
        name="idle",
        description="待机：自然站立，轻微呼吸起伏",
        pose_prompt=(
            "standing still in a neutral relaxed pose, arms slightly away from body, "
            "gentle breathing posture, weight evenly distributed"
        ),
        video_prompt=(
            "subtle idle breathing motion, gentle body sway side to side, "
            "very slight up and down movement, relaxed and calm"
        ),
        duration_secs=3.0,
        fps=12,
        loop=True,
    ),
    ActionDef(
        name="happy",
        description="开心：兴奋跳跃，双臂高举",
        pose_prompt=(
            "joyful jumping pose, both arms raised high above head, legs slightly spread, "
            "big happy expression, body elevated mid-bounce"
        ),
        video_prompt=(
            "excited bouncing motion, jumping up and down joyfully, arms pumping upward, "
            "body squashing and stretching with each bounce"
        ),
        duration_secs=1.5,
        fps=12,
        loop=True,
    ),
    ActionDef(
        name="sleepy",
        description="困倦：站立打瞌睡，身体摇晃",
        pose_prompt=(
            "drowsy standing pose, head drooping forward, eyes half closed, "
            "shoulders slumped, arms hanging loosely, slightly hunched posture"
        ),
        video_prompt=(
            "slow drowsy swaying, head nodding off then jerking back up, "
            "body rocking gently side to side, heavy tired breathing rhythm"
        ),
        duration_secs=3.0,
        fps=8,
        loop=True,
    ),
    ActionDef(
        name="hungry",
        description="饥饿：双手捂肚，虚弱摇晃",
        pose_prompt=(
            "hungry weak pose, both hands holding stomach, slightly hunched forward, "
            "tired expression, knees slightly bent, low energy posture"
        ),
        video_prompt=(
            "weak swaying motion, hands rubbing stomach, slight trembling from hunger, "
            "head lowering and lifting slowly, low energy movement"
        ),
        duration_secs=2.0,
        fps=12,
        loop=True,
    ),
    ActionDef(
        name="dance",
        description="跳舞：欢快律动，手臂摆动",
        pose_prompt=(
            "dynamic dancing pose, one arm raised and one arm out to the side, "
            "hips shifted to one side, one leg bent, energetic joyful expression"
        ),
        video_prompt=(
            "rhythmic dancing motion, hips swaying side to side, arms swinging to a beat, "
            "bouncing on the feet, full body groove, upbeat and lively"
        ),
        duration_secs=3.0,
        fps=12,
        loop=True,
    ),
    ActionDef(
        name="sleep",
        description="睡觉：躺卧熟睡，平稳呼吸",
        pose_prompt=(
            "lying down asleep in a curled relaxed position, eyes closed, "
            "peaceful expression, arms resting gently, body fully at rest"
        ),
        video_prompt=(
            "very slow deep breathing while sleeping, gentle rise and fall of the body, "
            "occasional tiny twitch, calm and completely still otherwise"
        ),
        duration_secs=4.0,
        fps=8,
        loop=True,
    ),
    ActionDef(
        name="wave",
        description="挥手：抬起一只手左右挥动",
        pose_prompt=(
            "friendly waving pose, one arm raised with hand open near head height, "
            "other arm relaxed at side, smiling welcoming expression"
        ),
        video_prompt=(
            "hand waving side to side in a friendly greeting, arm raised and "
            "waving back and forth, slight body lean toward the viewer, cheerful"
        ),
        duration_secs=2.0,
        fps=12,
        loop=False,
    ),
    ActionDef(
        name="yawn",
        description="打哈欠：张嘴伸懒腰",
        pose_prompt=(
            "mid-yawn pose, mouth wide open, eyes squeezed shut, head tilted back slightly, "
            "hands near face, stretched tired expression"
        ),
        video_prompt=(
            "slow yawning motion, mouth opening wide then closing, head tilting back, "
            "eyes closing tightly, body relaxing after the yawn"
        ),
        duration_secs=2.0,
        fps=12,
        loop=False,
    ),
    ActionDef(
        name="stretch",
        description="伸展：双臂上举拉伸身体",
        pose_prompt=(
            "full body stretch pose, both arms reaching high above head, "
            "body elongated upward, on tiptoes, refreshed expression"
        ),
        video_prompt=(
            "stretching motion, arms reaching up and body elongating, rising onto tiptoes, "
            "then relaxing back down, refreshing full body stretch"
        ),
        duration_secs=2.0,
        fps=12,
        loop=False,
    ),
    ActionDef(
        name="look_around",
        description="张望：左右转头观察",
        pose_prompt=(
            "curious looking pose, head turned to one side, hand near brow shading eyes, "
            "alert attentive expression, body leaning slightly forward"
        ),
        video_prompt=(
            "looking around curiously, head turning left then right, "
            "scanning the surroundings, slight body shifts with each glance, alert and curious"
        ),
        duration_secs=2.5,
        fps=12,
        loop=True,
    ),
]
