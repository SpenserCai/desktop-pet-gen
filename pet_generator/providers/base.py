"""Provider 抽象接口定义。

所有图像生成、视频生成、视觉理解 Provider 的基类与公共数据结构。
面向接口编程 — 上层管线仅依赖这些抽象，不感知具体实现。

设计原则:
- GenerationResult 统一返回格式，success=False 时 error 必有值
- 所有 I/O 方法接收 Path，返回 GenerationResult（不抛异常）
- 抽象方法签名使用 keyword-only 参数，防止位置参数误用
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GenerationResult:
    """生成任务的统一结果。

    Attributes:
        success: 是否成功
        output_paths: 生成的文件路径列表
        error: 失败时的错误信息
        metadata: 附加元数据（model, task_id, duration 等）
    """

    success: bool
    output_paths: list[Path] = field(default_factory=list)
    error: str | None = None
    metadata: dict = field(default_factory=dict)

    def __bool__(self) -> bool:
        """允许 `if result:` 判断成功与否。"""
        return self.success

    @property
    def first_path(self) -> Path | None:
        """便捷访问第一个输出文件。"""
        return self.output_paths[0] if self.output_paths else None


class ImageGenProvider(ABC):
    """图像生成 Provider 抽象基类。

    实现者需保证:
    - generate() 和 edit() 不抛异常，错误通过 GenerationResult.error 返回
    - output_dir 不存在时自动创建
    - 输出文件为 PNG 格式
    """

    @abstractmethod
    def generate(
        self,
        prompt: str,
        output_dir: Path,
        *,
        size: str = "1024x1024",
        quality: str = "medium",
        n: int = 1,
    ) -> GenerationResult:
        """文生图。

        Args:
            prompt: 图像描述提示词
            output_dir: 输出目录
            size: 图像尺寸 (WxH)
            quality: 质量等级 (low|medium|high)
            n: 生成数量

        Returns:
            GenerationResult，output_paths 包含生成的 PNG 文件路径
        """
        ...

    @abstractmethod
    def edit(
        self,
        image_paths: list[Path],
        prompt: str,
        output_dir: Path,
        *,
        size: str = "1024x1024",
        quality: str = "medium",
    ) -> GenerationResult:
        """基于参考图的图像编辑/生成。

        Args:
            image_paths: 参考图路径列表（支持多图输入）
            prompt: 编辑指令提示词
            output_dir: 输出目录
            size: 输出图像尺寸
            quality: 质量等级

        Returns:
            GenerationResult
        """
        ...

    @property
    def supports_edit(self) -> bool:
        """是否支持图像编辑（默认 True，子类可覆盖）。"""
        return True


class VideoGenProvider(ABC):
    """视频生成 Provider 抽象基类。

    实现者需保证:
    - 异步任务模式：提交 → 轮询 → 下载
    - 超时与错误通过 GenerationResult 返回
    - 输出文件为 MP4 格式
    """

    @abstractmethod
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
        """图生视频（首帧 → 视频，可选尾帧约束）。

        Args:
            first_frame: 首帧图片路径
            output_dir: 输出目录
            prompt: 运动描述提示词
            last_frame: 尾帧图片路径（可选，用于关键帧插值）
            duration: 视频时长（秒）
            resolution: 分辨率 (720P|1080P)

        Returns:
            GenerationResult，output_paths 包含 MP4 文件路径
        """
        ...

    @abstractmethod
    def text_to_video(
        self,
        prompt: str,
        output_dir: Path,
        *,
        duration: int = 5,
        resolution: str = "720P",
    ) -> GenerationResult:
        """文生视频。

        Args:
            prompt: 视频描述提示词
            output_dir: 输出目录
            duration: 视频时长（秒）
            resolution: 分辨率

        Returns:
            GenerationResult
        """
        ...

    @property
    def supports_last_frame(self) -> bool:
        """是否支持尾帧约束（默认 False，子类可覆盖）。"""
        return False


class VisionProvider(ABC):
    """视觉理解 Provider 抽象基类。

    提供图像描述与结构化分类能力。
    """

    @abstractmethod
    def describe(self, image_path: Path, prompt: str = "Describe this image in detail.") -> str:
        """对图片进行视觉理解，返回文本描述。

        Args:
            image_path: 图片路径
            prompt: 引导提示词

        Returns:
            文本描述（失败时返回 "[Vision Error] ..." 格式的错误信息）
        """
        ...

    @abstractmethod
    def classify(
        self,
        image_path: Path,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        """结构化分类 — 使用 JSON mode 获取结构化输出。

        Args:
            image_path: 图片路径
            system_prompt: 系统提示词（定义分类规则与输出格式）
            user_prompt: 用户提示词

        Returns:
            解析后的 JSON 字典。失败时返回 {"error": "..."} 格式。
        """
        ...
