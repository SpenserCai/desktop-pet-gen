"""阿里云百炼 WAN 2.7 图像生成 Provider。

使用 DashScope 异步任务 API 进行文生图。
仅依赖 Python 标准库（urllib），无额外第三方依赖。

特性:
- 异步任务模式：提交 → 轮询 → 下载
- 通过 ProviderSettings 注入配置
- 仅支持 generate()（不支持 edit）
- 可配置轮询间隔与超时

环境变量（由 ProviderSettings 指定）:
    DASHSCOPE_API_KEY: 百炼 API 密钥
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path

from pet_generator.config.settings import ProviderSettings
from pet_generator.providers.base import GenerationResult, ImageGenProvider

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 3  # 秒
_TIMEOUT = 300  # 5 分钟超时


class BailianImageProvider(ImageGenProvider):
    """百炼 WAN 2.7 图像生成（异步任务模式）。

    Args:
        settings: Provider 配置（含 DashScope 凭据与模型参数）
        poll_interval: 轮询间隔（秒）
        task_timeout: 任务超时（秒）
    """

    def __init__(
        self,
        settings: ProviderSettings | None = None,
        *,
        poll_interval: int = _POLL_INTERVAL,
        task_timeout: int = _TIMEOUT,
    ) -> None:
        self._settings = settings or ProviderSettings()
        self._poll_interval = poll_interval
        self._task_timeout = task_timeout
        self._base_url = self._settings.dashscope_base_url

    @property
    def _api_key(self) -> str:
        return self._settings.dashscope_api_key

    @property
    def _model(self) -> str:
        return self._settings.wan_image_model

    @property
    def _image_endpoint(self) -> str:
        return f"{self._base_url}/api/v1/services/aigc/image-generation/generation"

    def _api_request(
        self,
        url: str,
        *,
        method: str = "GET",
        body: dict | None = None,
        extra_headers: dict | None = None,
    ) -> dict:
        """发送 HTTP 请求到 DashScope API。"""
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if extra_headers:
            headers.update(extra_headers)

        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _poll_task(self, task_id: str) -> dict:
        """轮询任务直到完成或超时。"""
        url = f"{self._base_url}/api/v1/tasks/{task_id}"
        terminal = {"SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN"}
        start = time.time()

        while True:
            elapsed = time.time() - start
            if elapsed > self._task_timeout:
                raise TimeoutError(f"Task {task_id} timed out after {self._task_timeout}s")

            result = self._api_request(url)
            status = result.get("output", {}).get("task_status", "UNKNOWN")

            if status in terminal:
                return result

            logger.debug("Task %s status: %s (%.0fs elapsed)", task_id, status, elapsed)
            time.sleep(self._poll_interval)

    def _download_file(self, url: str, dest: Path) -> Path:
        """下载文件到本地。"""
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=120) as resp:
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
        return dest

    def generate(
        self,
        prompt: str,
        output_dir: Path,
        *,
        size: str = "1024x1024",
        quality: str = "medium",
        n: int = 1,
    ) -> GenerationResult:
        """文生图：提交异步任务 → 轮询 → 下载结果。"""
        try:
            # 百炼 size 格式为 "宽*高"
            bl_size = size.replace("x", "*")
            body = {
                "model": self._model,
                "input": {
                    "messages": [{"role": "user", "content": [{"text": prompt}]}],
                },
                "parameters": {"size": bl_size, "n": n},
            }

            logger.info("Bailian image generate: model=%s, size=%s, n=%d", self._model, bl_size, n)

            # 提交任务
            result = self._api_request(
                self._image_endpoint,
                method="POST",
                body=body,
                extra_headers={"X-DashScope-Async": "enable"},
            )

            task_id = result.get("output", {}).get("task_id", "")
            if not task_id:
                return GenerationResult(
                    success=False,
                    error=f"No task_id in response: {json.dumps(result, ensure_ascii=False)}",
                )

            logger.info("Bailian task submitted: %s", task_id)

            # 轮询等待完成
            final = self._poll_task(task_id)
            status = final.get("output", {}).get("task_status", "")

            if status != "SUCCEEDED":
                msg = final.get("output", {}).get("message", "Unknown error")
                return GenerationResult(success=False, error=f"Task {status}: {msg}")

            # 提取结果 URL 并下载
            output_dir.mkdir(parents=True, exist_ok=True)
            urls = self._extract_urls(final)
            if not urls:
                return GenerationResult(success=False, error="No result URLs in task output")

            saved: list[Path] = []
            for i, url in enumerate(urls):
                suffix = f"_{i}" if len(urls) > 1 else ""
                dest = output_dir / f"{task_id}{suffix}.png"
                self._download_file(url, dest)
                saved.append(dest)

            logger.info("Bailian generate success: %d images → %s", len(saved), output_dir)
            return GenerationResult(
                success=True,
                output_paths=saved,
                metadata={"model": self._model, "task_id": task_id, "size": bl_size},
            )
        except Exception as e:
            logger.exception("Bailian generate failed")
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
        """图像编辑：WAN 2.7 不支持 edit。

        如需图像编辑功能，请使用 AzureGptImageProvider。
        """
        return GenerationResult(
            success=False,
            error=(
                "BailianImageProvider does not support edit(). "
                "Use AzureGptImageProvider for image editing."
            ),
        )

    @property
    def supports_edit(self) -> bool:
        return False

    @staticmethod
    def _extract_urls(result: dict) -> list[str]:
        """从任务结果中提取输出文件 URL。"""
        output = result.get("output", {})
        urls: list[str] = []
        # 格式 1: results[].url
        for item in output.get("results", []):
            u = item.get("url") or ""
            if u:
                urls.append(u)
        # 格式 2: choices[].message.content[].image
        for choice in output.get("choices", []):
            msg = choice.get("message", {})
            for content in msg.get("content", []):
                u = content.get("image") or ""
                if u:
                    urls.append(u)
        return urls
