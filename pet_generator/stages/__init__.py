"""管线阶段模块 — 7 个 Stage 的统一入口。

导出所有 Stage 类与核心数据结构，供 pipeline 编排层使用：

    from pet_generator.stages import (
        Classifier, ClassificationResult,
        Standardizer,
        PoseGenerator,
        VideoGenerator,
        FrameExtractor,
        BackgroundRemover,
        SpritePacker,
    )

Stage 执行顺序:
    0. Classifier       — 智能分类（体型 / 材质 / 风格）
    1. Standardizer     — 分类感知标准化
    2. PoseGenerator    — 类型化尾帧生成
    3. VideoGenerator   — 过渡视频生成
    4. FrameExtractor   — 帧提取（ffmpeg）
    5. BackgroundRemover — 去背景（U2-Net ONNX）
    6. SpritePacker     — Sprite Sheet 打包 + manifest
"""

from __future__ import annotations

from .bg_remover import BackgroundRemover
from .classifier import ClassificationResult, Classifier
from .frame_extractor import FrameExtractor
from .pose_generator import PoseGenerator
from .sprite_packer import SpritePacker
from .standardizer import Standardizer
from .video_generator import VideoGenerator

__all__ = [
    # Stage 0
    "Classifier",
    "ClassificationResult",
    # Stage 1
    "Standardizer",
    # Stage 2
    "PoseGenerator",
    # Stage 3
    "VideoGenerator",
    # Stage 4
    "FrameExtractor",
    # Stage 5
    "BackgroundRemover",
    # Stage 6
    "SpritePacker",
]
