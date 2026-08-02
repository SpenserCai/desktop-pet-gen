"""Stage 4 帧提取 — ffmpeg 容错与真实抽帧。

容错路径全部用打桩（不依赖 ffmpeg 是否安装）；
真实抽帧用 ffmpeg 现场合成一段测试视频，缺 ffmpeg 时自动 skip。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from pet_generator.stages.frame_extractor import FrameExtractor

FFMPEG = shutil.which("ffmpeg")


# ---------------------------------------------------------------------------
# 容错：任何失败都必须返回空列表，由上层隔离该动作
# ---------------------------------------------------------------------------


def test_missing_ffmpeg_returns_empty(monkeypatch, tmp_path: Path):
    def _raise(*args, **kwargs):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(subprocess, "run", _raise)
    assert FrameExtractor().extract(tmp_path / "v.mp4", tmp_path / "out", fps=12) == []


def test_timeout_returns_empty(monkeypatch, tmp_path: Path):
    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=120)

    monkeypatch.setattr(subprocess, "run", _timeout)
    assert FrameExtractor().extract(tmp_path / "v.mp4", tmp_path / "out", fps=12) == []


def test_nonzero_returncode_returns_empty(monkeypatch, tmp_path: Path):
    class Proc:
        returncode = 1
        stderr = "moov atom not found"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Proc())
    assert FrameExtractor().extract(tmp_path / "v.mp4", tmp_path / "out", fps=12) == []


def test_corrupt_video_returns_empty(tmp_path: Path):
    """真实 ffmpeg 面对垃圾字节也只能返回空列表，不得抛异常。"""
    if not FFMPEG:
        pytest.skip("ffmpeg 不可用")
    video = tmp_path / "corrupt.mp4"
    video.write_bytes(b"\x00" * 4096)
    assert FrameExtractor().extract(video, tmp_path / "out", fps=12) == []


# ---------------------------------------------------------------------------
# 真实抽帧
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_extract_real_video_frames(tmp_path: Path):
    """用 ffmpeg 合成 1 秒测试图案视频后抽帧，验证帧数上限与命名有序。"""
    if not FFMPEG:
        pytest.skip("ffmpeg 不可用")
    video = tmp_path / "sample.mp4"
    subprocess.run(
        [
            FFMPEG,
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=128x128:rate=12:duration=1",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        capture_output=True,
        check=True,
    )
    frames = FrameExtractor().extract(video, tmp_path / "out", fps=12, max_frames=5)
    assert 1 <= len(frames) <= 5, f"抽帧数 {len(frames)} 应受 max_frames 约束"
    assert frames == sorted(frames), "帧顺序必须与文件名排序一致（决定播放顺序）"
    assert all(f.suffix == ".png" and f.stat().st_size > 0 for f in frames)
