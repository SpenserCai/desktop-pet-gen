"""Vision Provider 子模块。

导出:
    VisionProvider: 抽象基类（从 providers.base 重导出）
    OpenAICompatibleVisionProvider: 通用 OpenAI SDK 实现
"""

from pet_generator.providers.base import VisionProvider
from pet_generator.providers.vision.openai_compatible import OpenAICompatibleVisionProvider

__all__ = [
    "OpenAICompatibleVisionProvider",
    "VisionProvider",
]
