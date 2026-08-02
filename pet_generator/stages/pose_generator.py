"""Stage 2: 类型化尾帧生成 — 为每个动作生成关键姿态（尾帧）静态图。

基于标准参考图，为每个动作的 ``pose_prompt`` 生成对应的尾帧图片。
尾帧将作为视频生成的 ``last_frame`` 约束，确保动画过渡到目标姿态。

并发性:
- 使用 ThreadPoolExecutor + as_completed 并发生成各动作尾帧（I/O 密集，
  GIL 不构成瓶颈），范式与 video_generator.py 保持一致。
- 每个动作使用独立临时子目录隔离 Provider 的秒级时间戳临时文件名，
  杜绝并发撞名导致的错图/失败（并发扩展规范见 docs/standards/EXTEND_MECHANISMS.md）。

错误处理:
- 单个动作生成失败 → warn + skip（不阻塞其他动作）
- 返回成功生成的 {action_name: path} 字典
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pet_generator.config.actions.base import ActionDef
from pet_generator.prompts import get_pose_prompt
from pet_generator.providers.base import ImageGenProvider

logger = logging.getLogger(__name__)


class PoseGenerator:
    """Stage 2 — 类型化尾帧生成。

    Args:
        image_provider: 图像生成/编辑 Provider（已初始化）。
        max_workers: 并发动作数上限。尾帧生成为 I/O 密集（Azure edit 同步阻塞
            ~40s/次），线程池即可高效并行，GIL 不构成瓶颈。默认 3，兼顾速度
            与 Azure 图像 API 限流安全；如遇 429/throttling 可调小（如 2），
            长期稳定无 429 可调大到 4。
    """

    def __init__(self, image_provider: ImageGenProvider, max_workers: int = 3) -> None:
        self._image_provider = image_provider
        self._max_workers = max_workers

    def run(
        self,
        standard_image: Path,
        actions: list[ActionDef],
        body_type: str,
        output_dir: Path,
    ) -> dict[str, Path]:
        """为每个动作并发生成尾帧图片。

        每个动作独立调用图像编辑 Provider，互不阻塞。单个动作失败仅
        warn + skip，不影响其它动作。

        线程安全说明: 每个动作写入各自唯一目标文件 output_dir/{action.name}.png，
        并使用独立临时子目录 output_dir/.tmp_{action.name} 隔离 Provider 的
        秒级时间戳临时文件名；output_dir.mkdir 与各 tmp_dir.mkdir 均幂等，
        动作之间无共享可变状态；pose_images 字典仅在【主线程】通过 as_completed
        串行更新，避免竞态。

        Args:
            standard_image: Stage 1 生成的标准参考图。
            actions: 需要生成的动作列表。
            body_type: 体型（决定 pose prompt 的约束模板）。
            output_dir: 输出目录（不存在时自动创建）。

        Returns:
            {action_name: pose_image_path} — 仅包含成功生成的动作。
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        pose_images: dict[str, Path] = {}

        if not actions:
            logger.info("尾帧生成完成: 0/0 成功")
            return pose_images

        logger.info(
            "开始并发生成尾帧: 共 %d 个动作, max_workers=%d",
            len(actions),
            self._max_workers,
        )

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            # 提交全部动作 — 并发执行图像编辑
            future_to_action = {
                executor.submit(
                    self._generate_single,
                    standard_image,
                    action,
                    body_type,
                    output_dir,
                ): action
                for action in actions
            }

            # 在主线程按完成顺序收集结果，串行更新 pose_images，避免竞态
            for future in as_completed(future_to_action):
                action = future_to_action[future]
                try:
                    pose_path = future.result()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("尾帧生成失败，跳过动作 '%s': %s", action.name, exc)
                    continue
                pose_images[action.name] = pose_path
                logger.info("尾帧已生成: %s → %s", action.name, pose_path)

        logger.info("尾帧生成完成: %d/%d 成功", len(pose_images), len(actions))
        return pose_images

    def _generate_single(
        self,
        standard_image: Path,
        action: ActionDef,
        body_type: str,
        output_dir: Path,
    ) -> Path:
        """生成单个动作的尾帧。

        Raises:
            RuntimeError: 生成失败。
        """
        # 1. 组装 pose prompt
        prompt = get_pose_prompt(body_type, action.pose_prompt)

        # 2. 每动作独立临时子目录 → 隔离 Provider 的秒级时间戳临时文件名，
        #    杜绝并发撞名（action.name 在动作集内唯一 → .tmp_* 子目录互异）。
        #    tmp_dir 与 target 同属 output_dir 子树、处于同一文件系统，
        #    跨目录 Path.replace() 仍为原子重命名。
        tmp_dir = output_dir / f".tmp_{action.name}"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        # 3. 调用图像编辑（临时产物落入本动作专属子目录）
        result = self._image_provider.edit(
            image_paths=[standard_image],
            prompt=prompt,
            output_dir=tmp_dir,
        )

        # 4. 校验
        if not result.success or result.first_path is None:
            error_msg = result.error or "未知错误（无输出文件）"
            raise RuntimeError(f"尾帧生成失败: {error_msg}")

        # 5. 规范化落盘文件名为动作名，便于调试与下游追溯。
        #    Provider 输出文件名带时间戳/task_id（不可读），而 action.name 在动作集内唯一；
        #    下游仅依赖字典 key 与每动作产物，不依赖原始文件名，故重命名安全。
        #    Path.replace() 为原子重命名，目标已存在则覆盖，保证重复运行幂等。
        target = output_dir / f"{action.name}.png"
        result.first_path.replace(target)
        return target
