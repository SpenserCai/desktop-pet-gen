"""Vision Provider 抽象基类（视觉领域扩展）。

从 providers.base 重导出 VisionProvider，并定义视觉领域的公共工具函数。
"""

from __future__ import annotations

import base64
from pathlib import Path

from pet_generator.providers.base import VisionProvider

__all__ = ["VisionProvider", "image_to_data_url"]

# 支持的图片 MIME 类型映射
_MIME_MAP: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


def image_to_data_url(image_path: Path) -> str:
    """将本地图片转为 base64 data URL。

    Args:
        image_path: 图片文件路径

    Returns:
        data:{mime};base64,{data} 格式的 URL

    Raises:
        FileNotFoundError: 图片文件不存在
        ValueError: 不支持的图片格式
    """
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    suffix = image_path.suffix.lower()
    mime = _MIME_MAP.get(suffix)
    if mime is None:
        raise ValueError(
            f"Unsupported image format '{suffix}'. Supported: {list(_MIME_MAP.keys())}"
        )

    b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"
