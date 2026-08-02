"""Stage 4: 帧提取 — 使用 ffmpeg 从视频中提取逐帧 PNG。

将 Stage 3 生成的过渡视频按指定帧率提取为 PNG 序列，
供后续去背景与精灵图打包使用。

依赖:
- 系统已安装 ffmpeg 且在 PATH 中可用。

错误处理:
- 视频损坏 / ffmpeg 不可用 → 返回空列表（warn），不阻塞其他动作。
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class FrameExtractor:
    """Stage 4 — 视频帧提取（ffmpeg）。

    无状态工具类，无需初始化参数。
    """

    def extract(
        self,
        video_path: Path,
        output_dir: Path,
        *,
        fps: int = 12,
        max_frames: int = 50,
    ) -> list[Path]:
        """使用 ffmpeg 从视频中提取帧。

        Args:
            video_path: 输入视频文件路径。
            output_dir: 帧图片输出目录（不存在时自动创建）。
            fps: 提取帧率。
            max_frames: 最大提取帧数（防止过长视频产生过多帧）。

        Returns:
            按序号排序的帧文件路径列表。视频损坏或 ffmpeg 失败时返回空列表。
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # 输出文件名模板: frame_0001.png, frame_0002.png, ...
        frame_pattern = str(output_dir / "frame_%04d.png")

        cmd = [
            "ffmpeg",
            "-nostdin",  # 禁止 ffmpeg 从 stdin 读交互命令，防止管道环境阻塞
            "-y",  # 覆盖已有文件
            "-i",
            str(video_path),
            "-vf",
            f"fps={fps}",
            "-frames:v",
            str(max_frames),
            frame_pattern,
        ]

        logger.info("提取帧: %s (fps=%d, max_frames=%d)", video_path.name, fps, max_frames)
        logger.debug("ffmpeg 命令: %s", " ".join(cmd))

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,  # 2 分钟超时保护
                stdin=subprocess.DEVNULL,  # 切断 stdin 继承，双保险防阻塞
            )
        except FileNotFoundError:
            logger.warning(
                "ffmpeg 未找到（请确认已安装并在 PATH 中）。跳过帧提取: %s",
                video_path,
            )
            return []
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg 超时（>120s）。跳过帧提取: %s", video_path)
            return []

        if proc.returncode != 0:
            # 截取 stderr 最后 500 字符作为错误摘要
            stderr_tail = proc.stderr[-500:] if proc.stderr else "(无 stderr)"
            logger.warning(
                "ffmpeg 失败 (returncode=%d): %s。视频: %s",
                proc.returncode,
                stderr_tail,
                video_path,
            )
            return []

        # 收集输出帧文件，按文件名排序（frame_0001 < frame_0002 < ...）
        frames = sorted(output_dir.glob("frame_*.png"))
        logger.info("帧提取完成: %s → %d 帧", video_path.name, len(frames))
        return frames
