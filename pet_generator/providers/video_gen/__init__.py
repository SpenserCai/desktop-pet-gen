"""Video Generation Provider 子模块。

导出:
    KlingVideoProvider: Kling 视频生成（支持首尾帧）
    BailianVideoProvider: WAN 2.7 视频生成（仅首帧）
"""

from pet_generator.providers.video_gen.bailian_video import BailianVideoProvider
from pet_generator.providers.video_gen.kling_video import KlingVideoProvider

__all__ = [
    "BailianVideoProvider",
    "KlingVideoProvider",
]
