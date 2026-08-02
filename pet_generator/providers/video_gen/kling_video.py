"""Kling 视频生成 Provider（通过百炼 DashScope API）。

支持首帧 + 尾帧约束的图生视频，是桌面宠物动画生成的核心 Provider。
- 模型: kling/kling-v3-omni-video-generation（可配置）
- 本地图片通过 base64 data URL 传入（百炼 API 支持此格式）
- 异步任务模式：提交 → 轮询（10s 间隔）→ 下载

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

# Kling v3-omni 拒绝 duration=1/2（报错 "duration value 'X' is invalid"），
# 实测有效下限为 3（接受 3 与 4）。此处仅强制下限，不加上限：上限未经证实，
# 且当前动作集最大时长仅 4s，无需上限约束。
_MIN_DURATION = 3


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


class KlingVideoProvider(VideoGenProvider):
    """Kling 视频生成（支持首帧 + 尾帧约束）。

    首尾帧模式是生成循环精灵动画的关键：首帧=正面标准图，尾帧=动作姿态图。

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
    def _model(self) -> str:
        return self._settings.kling_model

    @property
    def _video_endpoint(self) -> str:
        return f"{self._base_url}/api/v1/services/aigc/video-generation/video-synthesis"

    @property
    def supports_last_frame(self) -> bool:
        """Kling 支持尾帧约束。"""
        return True

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

            logger.debug("Kling task %s: %s (%.0fs)", task_id, status, elapsed)
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

        logger.info("Kling task submitted: %s", task_id)
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
        """图生视频：首帧（+ 可选尾帧）→ 视频。

        Kling 支持 first_frame + last_frame 约束，适合生成循环动画。
        本地图片自动转为 base64 data URL。
        """
        try:
            # 钳制 duration 到 Kling 有效下限（v3-omni 拒绝 1/2，接受 3/4）。
            # 仅强制下限，不加上限。原始值小于下限时打 INFO 日志便于追溯。
            original_duration = duration
            duration = max(_MIN_DURATION, int(duration))
            if original_duration < _MIN_DURATION:
                logger.info(
                    "Kling duration 钳制: %s → %s (Kling 有效下限 3s)",
                    original_duration,
                    duration,
                )

            if not first_frame.exists():
                return GenerationResult(
                    success=False, error=f"First frame not found: {first_frame}"
                )

            # 构建 media 数组
            first_frame_url = _image_to_data_url(first_frame)
            media: list[dict] = [{"type": "first_frame", "url": first_frame_url}]

            if last_frame is not None:
                if not last_frame.exists():
                    return GenerationResult(
                        success=False, error=f"Last frame not found: {last_frame}"
                    )
                last_frame_url = _image_to_data_url(last_frame)
                media.append({"type": "last_frame", "url": last_frame_url})

            input_data: dict = {"media": media}
            if prompt:
                input_data["prompt"] = prompt

            body = {
                "model": self._model,
                "input": input_data,
                "parameters": {
                    "duration": duration,
                    "mode": "std",
                    "aspect_ratio": "1:1",
                },
            }

            logger.info(
                "Kling i2v: model=%s, duration=%d, last_frame=%s",
                self._model,
                duration,
                last_frame is not None,
            )

            final = self._submit_and_wait(body)

            # 下载结果
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

            logger.info("Kling i2v success: %s", saved)
            return GenerationResult(
                success=True,
                output_paths=saved,
                metadata={
                    "model": self._model,
                    "task_id": task_id,
                    "duration": duration,
                    "has_last_frame": last_frame is not None,
                },
            )
        except Exception as e:
            logger.exception("Kling i2v failed")
            return GenerationResult(success=False, error=str(e))

    def text_to_video(
        self,
        prompt: str,
        output_dir: Path,
        *,
        duration: int = 5,
        resolution: str = "720P",
    ) -> GenerationResult:
        """文生视频。"""
        try:
            # 与 image_to_video 保持一致：钳制 duration 到 Kling 有效下限。
            original_duration = duration
            duration = max(_MIN_DURATION, int(duration))
            if original_duration < _MIN_DURATION:
                logger.info(
                    "Kling duration 钳制: %s → %s (Kling 有效下限 3s)",
                    original_duration,
                    duration,
                )

            body = {
                "model": self._model,
                "input": {"prompt": prompt},
                "parameters": {
                    "duration": duration,
                    "mode": "std",
                    "aspect_ratio": "1:1",
                },
            }

            logger.info("Kling t2v: model=%s, duration=%d", self._model, duration)
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

            logger.info("Kling t2v success: %s", saved)
            return GenerationResult(
                success=True,
                output_paths=saved,
                metadata={"model": self._model, "task_id": task_id, "duration": duration},
            )
        except Exception as e:
            logger.exception("Kling t2v failed")
            return GenerationResult(success=False, error=str(e))
