"""Azure OpenAI GPT-Image-2 图像生成 Provider。

使用 Azure OpenAI 的 gpt-image-2 模型进行文生图和图像编辑。
- generate: 标准文生图
- edit: 支持多图输入的图像编辑（核心能力 — 用于标准化与姿态生成）

特性:
- 通过 ProviderSettings 注入配置（endpoint, api_key, model, api_version）
- 延迟创建 AzureOpenAI 客户端
- edit() 支持多图输入（list[Path]）
- 输出 b64_json → 本地 PNG 文件

环境变量（由 ProviderSettings 指定）:
    AZURE_OPENAI_API_KEY: Azure OpenAI API 密钥
    AZURE_OPENAI_ENDPOINT: Azure OpenAI 服务端点
"""

from __future__ import annotations

import base64
import logging
import time
from pathlib import Path

from pet_generator.config.settings import ProviderSettings
from pet_generator.providers.base import GenerationResult, ImageGenProvider

logger = logging.getLogger(__name__)


class AzureGptImageProvider(ImageGenProvider):
    """Azure OpenAI GPT-Image-2 图像生成。

    Args:
        settings: Provider 配置（含 Azure 凭据与模型参数）
    """

    def __init__(self, settings: ProviderSettings | None = None) -> None:
        self._settings = settings or ProviderSettings()

    def _get_client(self):
        """创建 AzureOpenAI 客户端（延迟导入，按需创建）。"""
        from openai import AzureOpenAI

        return AzureOpenAI(
            api_key=self._settings.azure_api_key,
            azure_endpoint=self._settings.azure_endpoint,
            api_version=self._settings.azure_api_version,
        )

    @property
    def _model(self) -> str:
        return self._settings.azure_model

    def generate(
        self,
        prompt: str,
        output_dir: Path,
        *,
        size: str = "1024x1024",
        quality: str = "medium",
        n: int = 1,
    ) -> GenerationResult:
        """文生图：调用 gpt-image-2 生成图像。"""
        try:
            client = self._get_client()
            logger.info(
                "Azure generate: model=%s, size=%s, quality=%s, n=%d", self._model, size, quality, n
            )

            result = client.images.generate(
                model=self._model,
                prompt=prompt,
                size=size,
                quality=quality,
                output_format="png",
                n=n,
            )

            output_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            saved: list[Path] = []

            for i, item in enumerate(result.data):
                b64 = item.b64_json
                if not b64:
                    continue
                out_path = output_dir / f"{ts}_{i}.png"
                out_path.write_bytes(base64.b64decode(b64))
                saved.append(out_path)

            if not saved:
                return GenerationResult(success=False, error="No images in response")

            logger.info("Azure generate success: %d images → %s", len(saved), output_dir)
            return GenerationResult(
                success=True,
                output_paths=saved,
                metadata={"model": self._model, "size": size, "quality": quality},
            )
        except Exception as e:
            logger.exception("Azure generate failed")
            return GenerationResult(success=False, error=str(e))

    def edit(
        self,
        image_paths: list[Path],
        prompt: str,
        output_dir: Path,
        *,
        size: str = "1024x1024",
        quality: str = "medium",
    ) -> GenerationResult:
        """图像编辑：基于参考图 + 提示词生成新图像。

        支持多图输入 — 用于将原始宠物图 + 标准正面图作为参考。
        """
        file_handles = []
        try:
            client = self._get_client()
            logger.info(
                "Azure edit: model=%s, %d ref images, size=%s",
                self._model,
                len(image_paths),
                size,
            )

            # 打开所有参考图文件
            for p in image_paths:
                if not p.exists():
                    return GenerationResult(success=False, error=f"Reference image not found: {p}")
                file_handles.append(open(p, "rb"))  # noqa: SIM115

            image_arg = file_handles if len(file_handles) > 1 else file_handles[0]

            result = client.images.edit(
                model=self._model,
                image=image_arg,
                prompt=prompt,
                size=size,
                quality=quality,
            )

            output_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            saved: list[Path] = []

            for i, item in enumerate(result.data):
                b64 = item.b64_json
                if not b64:
                    continue
                out_path = output_dir / f"{ts}_edited_{i}.png"
                out_path.write_bytes(base64.b64decode(b64))
                saved.append(out_path)

            if not saved:
                return GenerationResult(success=False, error="No images in edit response")

            logger.info("Azure edit success: %d images → %s", len(saved), output_dir)
            return GenerationResult(
                success=True,
                output_paths=saved,
                metadata={"model": self._model, "size": size, "quality": quality, "mode": "edit"},
            )
        except Exception as e:
            logger.exception("Azure edit failed")
            return GenerationResult(success=False, error=str(e))
        finally:
            for fh in file_handles:
                fh.close()

    @property
    def supports_edit(self) -> bool:
        return True
