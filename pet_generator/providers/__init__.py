"""Provider 层：图像生成、视频生成、视觉理解的统一接口与工厂。

工厂函数根据配置名称创建对应的 Provider 实例，实现依赖注入与运行时切换。

Usage:
    from pet_generator.providers import create_image_provider, create_video_provider
    from pet_generator.config import Settings

    settings = Settings.from_env()
    img_gen = create_image_provider(settings.providers.image_provider, settings.providers)
    vid_gen = create_video_provider(settings.providers.video_provider, settings.providers)
"""

from __future__ import annotations

from pet_generator.config.settings import ClassifierSettings, ProviderSettings
from pet_generator.providers.base import (
    GenerationResult,
    ImageGenProvider,
    VideoGenProvider,
    VisionProvider,
)

__all__ = [
    "GenerationResult",
    "ImageGenProvider",
    "VideoGenProvider",
    "VisionProvider",
    "create_image_provider",
    "create_video_provider",
    "create_vision_provider",
]

# 注册表：名称 → 类路径（延迟导入避免循环依赖）
_IMAGE_PROVIDERS: dict[str, str] = {
    "azure": "pet_generator.providers.image_gen.azure_gpt_image.AzureGptImageProvider",
    "bailian": "pet_generator.providers.image_gen.bailian_image.BailianImageProvider",
}

_VIDEO_PROVIDERS: dict[str, str] = {
    "kling": "pet_generator.providers.video_gen.kling_video.KlingVideoProvider",
    "wan27": "pet_generator.providers.video_gen.bailian_video.BailianVideoProvider",
}


def _import_class(dotted_path: str):
    """动态导入类（延迟加载，避免未使用的 Provider 触发导入错误）。"""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def create_image_provider(
    name: str,
    settings: ProviderSettings | None = None,
) -> ImageGenProvider:
    """创建图像生成 Provider 实例。

    Args:
        name: Provider 名称 ("azure" | "bailian")
        settings: Provider 配置（None 时使用默认配置）

    Returns:
        ImageGenProvider 实例

    Raises:
        ValueError: 未知的 Provider 名称
    """
    if name not in _IMAGE_PROVIDERS:
        available = ", ".join(sorted(_IMAGE_PROVIDERS.keys()))
        raise ValueError(f"Unknown image provider '{name}'. Available: {available}")

    cls = _import_class(_IMAGE_PROVIDERS[name])
    return cls(settings=settings)


def create_video_provider(
    name: str,
    settings: ProviderSettings | None = None,
) -> VideoGenProvider:
    """创建视频生成 Provider 实例。

    Args:
        name: Provider 名称 ("kling" | "wan27")
        settings: Provider 配置（None 时使用默认配置）

    Returns:
        VideoGenProvider 实例

    Raises:
        ValueError: 未知的 Provider 名称
    """
    if name not in _VIDEO_PROVIDERS:
        available = ", ".join(sorted(_VIDEO_PROVIDERS.keys()))
        raise ValueError(f"Unknown video provider '{name}'. Available: {available}")

    cls = _import_class(_VIDEO_PROVIDERS[name])
    return cls(settings=settings)


def create_vision_provider(
    settings: ClassifierSettings | None = None,
) -> VisionProvider:
    """创建视觉理解 Provider 实例。

    当前唯一实现为 OpenAI 兼容格式（支持 DashScope Qwen-VL 等）。

    Args:
        settings: 分类器配置（None 时使用默认配置）

    Returns:
        VisionProvider 实例
    """
    from pet_generator.providers.vision.openai_compatible import OpenAICompatibleVisionProvider

    return OpenAICompatibleVisionProvider(settings=settings)
