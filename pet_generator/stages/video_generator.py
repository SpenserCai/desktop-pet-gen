"""Stage 3: 过渡视频生成 — 从标准图到各动作尾帧的过渡动画。

使用视频生成 Provider，以标准图为首帧、动作尾帧为尾帧约束，
生成每个动作的过渡视频。视频后续将被提取为逐帧精灵动画。

错误处理:
- 单个动作视频生成失败 → warn + skip（不阻塞其他动作）
- 返回成功生成的 {action_name: video_path} 字典
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pet_generator.config.actions.base import ActionDef
from pet_generator.prompts import get_video_prompt
from pet_generator.providers.base import VideoGenProvider

logger = logging.getLogger(__name__)


class VideoGenerator:
    """Stage 3 — 过渡视频生成。

    Args:
        video_provider: 视频生成 Provider（已初始化）。
        max_workers: 并发动作数上限。视频生成为 I/O 密集（提交 Kling 异步任务
            + 阻塞轮询 + 下载），线程池即可高效并行，GIL 不构成瓶颈。
            默认 5，兼顾生成速度与 DashScope 限流安全；如遇 429/throttling
            可调小（如 3 或 2）。
    """

    def __init__(self, video_provider: VideoGenProvider, max_workers: int = 5) -> None:
        self._video_provider = video_provider
        self._max_workers = max_workers

    def run(
        self,
        standard_image: Path,
        pose_images: dict[str, Path],
        actions: list[ActionDef],
        output_dir: Path,
    ) -> dict[str, Path]:
        """为每个动作并发生成过渡视频。

        每个动作独立提交 Kling 异步任务并并行轮询，互不阻塞。单个动作失败
        仅 warn + skip，不影响其它动作。

        线程安全说明: 每个动作写入各自唯一目标文件 output_dir/{action.name}.mp4，
        output_dir.mkdir 幂等，动作之间无共享可变状态；videos 字典仅在【主线程】
        通过 as_completed 串行更新，避免竞态。

        Args:
            standard_image: Stage 1 的标准参考图（作为视频首帧）。
            pose_images: Stage 2 的尾帧字典 {action_name: path}。
            actions: 需要生成的动作列表。
            output_dir: 输出目录（不存在时自动创建）。

        Returns:
            {action_name: video_path} — 仅包含成功生成的动作。
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        videos: dict[str, Path] = {}

        if not actions:
            logger.info("视频生成完成: 0/0 成功")
            return videos

        logger.info(
            "开始并发生成视频: 共 %d 个动作, max_workers=%d",
            len(actions),
            self._max_workers,
        )

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            # 提交全部动作 — 并发提交 + 并行轮询
            future_to_action = {
                executor.submit(
                    self._generate_single,
                    standard_image,
                    action,
                    pose_images,
                    output_dir,
                ): action
                for action in actions
            }

            # 在主线程按完成顺序收集结果，串行更新 videos，避免竞态
            for future in as_completed(future_to_action):
                action = future_to_action[future]
                try:
                    video_path = future.result()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("视频生成失败，跳过动作 '%s': %s", action.name, exc)
                    continue
                videos[action.name] = video_path
                logger.info("视频已生成: %s → %s", action.name, video_path)

        logger.info("视频生成完成: %d/%d 成功", len(videos), len(actions))
        return videos

    def _generate_single(
        self,
        standard_image: Path,
        action: ActionDef,
        pose_images: dict[str, Path],
        output_dir: Path,
    ) -> Path:
        """生成单个动作的过渡视频。

        Raises:
            RuntimeError: 生成失败。
        """
        logger.info(
            "生成视频: %s (duration=%.1fs, loop=%s)",
            action.name,
            action.duration_secs,
            action.loop,
        )

        # 1. 组装视频 prompt
        prompt = get_video_prompt(action.video_prompt, loop=action.loop)

        # 2. 获取尾帧（可选 — 如果 Stage 2 该动作失败则无尾帧）
        last_frame = pose_images.get(action.name)
        if last_frame is None:
            logger.info("动作 '%s' 无尾帧约束，仅使用首帧 + prompt 生成", action.name)

        # 3. 调用视频生成 Provider
        result = self._video_provider.image_to_video(
            first_frame=standard_image,
            output_dir=output_dir,
            prompt=prompt,
            last_frame=last_frame,
            duration=int(action.duration_secs),
        )

        # 4. 校验
        if not result.success or result.first_path is None:
            error_msg = result.error or "未知错误（无输出文件）"
            raise RuntimeError(f"视频生成失败: {error_msg}")

        # 5. 规范化落盘文件名为动作名，便于调试与下游追溯。
        #    Provider 输出文件名为 task_id（不可读），而 action.name 在动作集内唯一；
        #    下游帧提取/打包仅依赖字典 key 与每动作子目录，不依赖原始文件名，故重命名安全。
        #    Path.replace() 为同目录原子重命名，目标已存在则覆盖，保证重复运行幂等。
        target = output_dir / f"{action.name}.mp4"
        result.first_path.replace(target)
        return target
