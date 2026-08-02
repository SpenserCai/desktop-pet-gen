"""阿里云百炼 WAN 2.7 视频生成 Provider（备选）。

支持图生视频（wan2.7-i2v）和文生视频（wan2.7-t2v）。
注意：WAN 2.7 i2v 不支持 last_frame，如传入则忽略并记录警告。

特性:
- 异步任务模式：提交 → 轮询 → 下载
- 通过 ProviderSettings 注入配置
- 仅支持首帧模式（supports_last_frame = False）

环境变量（由 ProviderSettings 指定）:
    DASHSCOPE_API_KEY: 百炼 API 密钥
"""

from __future__ import annotations

import base64
import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path

from pet_generator.config.settings import ProviderSettings
from pet_generator.providers.base import GenerationResult, VideoGenProvider

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 10  # 秒
_TIMEOUT = 600  # 10 分钟超时


def _image_to_data_url(image_path: Path) -> str:
    """将本地图片转为 base64 data URL。"""
    suffix = image_path.suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    mime = mime_map.get(suffix, "image/png")
    b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


class BailianVideoProvider(VideoGenProvider):
    """百炼 WAN 2.7 视频生成（备选，不支持 last_frame）。

    Args:
        settings: Provider 配置
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
    def _model_i2v(self) -> str:
        return self._settings.wan_i2v_model

    @property
    def _model_t2v(self) -> str:
        return self._settings.wan_t2v_model

    @property
    def _video_endpoint(self) -> str:
        return f"{self._base_url}/api/v1/services/aigc/video-generation/video-synthesis"

    @property
    def supports_last_frame(self) -> bool:
        """WAN 2.7 不支持尾帧约束。"""
        return False

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

            logger.debug("WAN task %s: %s (%.0fs)", task_id, status, elapsed)
            time.sleep(self._poll_interval)

    def _download_file(self, url: str, dest: Path) -> Path:
        """下载文件到本地。"""
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=300) as resp:
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
        return dest

    def _submit_and_wait(self, body: dict) -> dict:
        """提交任务并等待完成。"""
        result = self._api_request(
            self._video_endpoint,
            method="POST",
            body=body,
            extra_headers={"X-DashScope-Async": "enable"},
        )

        task_id = result.get("output", {}).get("task_id", "")
        if not task_id:
            raise RuntimeError(f"No task_id in response: {json.dumps(result, ensure_ascii=False)}")

        logger.info("WAN task submitted: %s", task_id)
        final = self._poll_task(task_id)
        status = final.get("output", {}).get("task_status", "")

        if status != "SUCCEEDED":
            msg = final.get("output", {}).get("message", "Unknown error")
            raise RuntimeError(f"Task {status}: {msg}")

        return final

    def _extract_video_urls(self, result: dict) -> list[str]:
        """从任务结果中提取视频 URL。"""
        output = result.get("output", {})
        urls: list[str] = []
        for item in output.get("results", []):
            u = item.get("url") or item.get("video_url") or ""
            if u:
                urls.append(u)
        u = output.get("video_url", "")
        if u:
            urls.append(u)
        return urls

    def image_to_video(
        self,
        first_frame: Path,
        output_dir: Path,
        *,
        prompt: str = "",
        last_frame: Path | None = None,
        duration: int = 5,
        resolution: str = "720P",
    ) -> GenerationResult:
        """图生视频（WAN 2.7 i2v）。

        注意：WAN 2.7 不支持 last_frame，如传入则忽略并记录警告。
        """
        if last_frame is not None:
            logger.warning(
                "BailianVideoProvider (WAN 2.7) does not support last_frame. "
                "Ignoring. Use KlingVideoProvider for first+last frame support."
            )

        try:
            if not first_frame.exists():
                return GenerationResult(
                    success=False, error=f"First frame not found: {first_frame}"
                )

            first_frame_url = _image_to_data_url(first_frame)

            input_data: dict = {"media": [{"type": "first_frame", "url": first_frame_url}]}
            if prompt:
                input_data["prompt"] = prompt

            body = {
                "model": self._model_i2v,
                "input": input_data,
                "parameters": {"duration": duration, "resolution": resolution},
            }

            logger.info(
                "WAN i2v: model=%s, duration=%d, resolution=%s",
                self._model_i2v,
                duration,
                resolution,
            )
            final = self._submit_and_wait(body)

            output_dir.mkdir(parents=True, exist_ok=True)
            urls = self._extract_video_urls(final)
            if not urls:
                return GenerationResult(success=False, error="No video URLs in task output")

            task_id = final.get("output", {}).get("task_id", "unknown")
            saved: list[Path] = []
            for i, url in enumerate(urls):
                suffix = f"_{i}" if len(urls) > 1 else ""
                dest = output_dir / f"{task_id}{suffix}.mp4"
                self._download_file(url, dest)
                saved.append(dest)

            logger.info("WAN i2v success: %s", saved)
            return GenerationResult(
                success=True,
                output_paths=saved,
                metadata={"model": self._model_i2v, "task_id": task_id, "duration": duration},
            )
        except Exception as e:
            logger.exception("WAN i2v failed")
            return GenerationResult(success=False, error=str(e))

    def text_to_video(
        self,
        prompt: str,
        output_dir: Path,
        *,
        duration: int = 5,
        resolution: str = "720P",
    ) -> GenerationResult:
        """文生视频（WAN 2.7 t2v）。"""
        try:
            body = {
                "model": self._model_t2v,
                "input": {"prompt": prompt},
                "parameters": {"duration": duration, "resolution": resolution},
            }

            logger.info("WAN t2v: model=%s, duration=%d", self._model_t2v, duration)
            final = self._submit_and_wait(body)

            output_dir.mkdir(parents=True, exist_ok=True)
            urls = self._extract_video_urls(final)
            if not urls:
                return GenerationResult(success=False, error="No video URLs in task output")

            task_id = final.get("output", {}).get("task_id", "unknown")
            saved: list[Path] = []
            for i, url in enumerate(urls):
                suffix = f"_{i}" if len(urls) > 1 else ""
                dest = output_dir / f"{task_id}{suffix}.mp4"
                self._download_file(url, dest)
                saved.append(dest)

            logger.info("WAN t2v success: %s", saved)
            return GenerationResult(
                success=True,
                output_paths=saved,
                metadata={"model": self._model_t2v, "task_id": task_id, "duration": duration},
            )
        except Exception as e:
            logger.exception("WAN t2v failed")
            return GenerationResult(success=False, error=str(e))
