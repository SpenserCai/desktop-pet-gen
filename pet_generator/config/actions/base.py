"""动作定义数据类。

每个桌面宠物的动画由一个 ``ActionDef`` 描述，包含：
- 用于生成"尾帧/关键姿态"静态图的 ``pose_prompt``
- 用于生成动画视频的 ``video_prompt``
- 时长 / 帧率 / 是否循环等运行时参数
- 对应 Rust 运行时枚举变体名 ``rust_variant``（自动从 ``name`` 推导）

设计取舍：
- ``rust_variant`` 采用 ``__post_init__`` 自动推导，避免在 4 套动作集中
  手写 PascalCase 造成的人为错误；若显式传入则以传入值为准（保留扩展点）。
- 数据类 frozen=False，便于上层在 pipeline 中按需复制/微调（``dataclasses.replace``）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


def snake_to_pascal(name: str) -> str:
    """将 snake_case 转换为 PascalCase。

    例：``tail_wag`` -> ``TailWag``，``look_around`` -> ``LookAround``。
    连续下划线 / 首尾下划线会被安全忽略。
    """
    return "".join(part.capitalize() for part in name.split("_") if part)


@dataclass
class ActionDef:
    """单个宠物动作的完整定义。

    Attributes:
        name: snake_case 动作标识（如 ``tail_wag``），在动作集内唯一。
        description: 中文描述，用于 CLI 展示与文档。
        pose_prompt: 尾帧/关键姿态生成 prompt（英文），描述静态姿势。
        video_prompt: 视频生成 prompt（英文），描述运动过程。
        duration_secs: 动画时长（秒）。
        fps: 帧率。
        loop: 是否循环播放。
        rust_variant: PascalCase 的 Rust 枚举变体名；为空则从 ``name`` 自动推导。
    """

    name: str
    description: str
    pose_prompt: str
    video_prompt: str
    duration_secs: float
    fps: int = 12
    loop: bool = True
    rust_variant: str = field(default="")

    def __post_init__(self) -> None:
        # 自动推导 rust_variant：snake_case -> PascalCase
        if not self.rust_variant:
            self.rust_variant = snake_to_pascal(self.name)

    @property
    def total_frames(self) -> int:
        """该动作的总帧数（用于运行时预分配 / 校验）。"""
        return max(1, int(round(self.duration_secs * self.fps)))
