"""管线编排器 — Stage 0~7 调度。

将单张宠物图片通过 AI 管线转化为可交互的桌面宠物精灵动画：
    Stage 0: 分类 → Stage 1: 标准化 → Stage 2: 尾帧 → Stage 3: 视频
    → Stage 4: 帧提取 → Stage 5: 去背景 → Stage 6: Sprite 打包
    → Stage 7: Rust 项目生成 + 编译

设计取舍：
- 各 Stage 通过延迟导入（lazy import）解耦，避免 stages 模块未就绪时
  阻塞 runtime_gen 的独立测试。
- skip_video 模式用 [标准图, 尾帧] 作为 2 帧 fallback，保证管线可端到端跑通。
- 每个 Stage 的输出目录带序号前缀，便于调试与断点续跑。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from pet_generator.config import Settings
from pet_generator.config.actions import get_actions

logger = logging.getLogger(__name__)


class Pipeline:
    """桌面宠物生成管线编排器。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        # 各阶段耗时记录（run() 开始时重置）
        self._stage_times: dict[str, float] = {}

    def run(self, input_image: Path) -> Path:
        """执行完整管线 Stage 0~7，返回最终产物路径。

        Args:
            input_image: 输入宠物图片路径。

        Returns:
            最终产物路径（编译后的二进制 或 项目目录）。

        Raises:
            FileNotFoundError: 输入图片不存在。
            RuntimeError: 管线执行失败。
        """
        if not input_image.exists():
            raise FileNotFoundError(f"Input image not found: {input_image}")

        start_time = time.time()
        # 各阶段耗时汇总（含 Stage 3/4，由 _stage_video_and_frames 内部填充）
        self._stage_times = {}
        logger.info("=" * 60)
        logger.info("Pipeline started: %s", input_image)
        logger.info("Pet name: %s", self.settings.pet_name)
        logger.info("=" * 60)

        dirs = self._setup_output_dirs()

        # ─── Stage 0: 分类 ────────────────────────────────────────────────
        t0 = time.time()
        logger.info("[Stage 0] 开始: 体型分类")
        classification = self._stage_classify(input_image, dirs["classification"])
        body_type = classification.body_type
        self._stage_times["Stage 0 分类"] = time.time() - t0
        logger.info(
            "[Stage 0] 完成: body_type=%s, 耗时 %.1fs",
            body_type,
            self._stage_times["Stage 0 分类"],
        )

        # ─── Stage 1: 标准化 ──────────────────────────────────────────────
        t1 = time.time()
        logger.info("[Stage 1] 开始: 图像标准化")
        standard_image = self._stage_standardize(input_image, classification, dirs["standard"])
        self._stage_times["Stage 1 标准化"] = time.time() - t1
        logger.info(
            "[Stage 1] 完成: %s, 耗时 %.1fs",
            standard_image,
            self._stage_times["Stage 1 标准化"],
        )

        # ─── Stage 2: 尾帧/姿态生成 ──────────────────────────────────────
        t2 = time.time()
        actions = get_actions(body_type, self.settings.selected_actions)
        logger.info("[Stage 2] 开始: 姿态/尾帧生成 (%d 个动作)", len(actions))
        pose_images = self._stage_poses(standard_image, actions, body_type, dirs["poses"])
        self._stage_times["Stage 2 姿态生成"] = time.time() - t2
        logger.info(
            "[Stage 2] 完成: %d 张姿态图, 耗时 %.1fs",
            len(pose_images),
            self._stage_times["Stage 2 姿态生成"],
        )

        # ─── Stage 3 & 4: 视频生成 + 帧提取 ──────────────────────────────
        action_frames = self._stage_video_and_frames(standard_image, pose_images, actions, dirs)

        # ─── Stage 4 后：空帧显式告警 + 下游隔离（§4.5）──────────────────
        empty_actions = [name for name, frames in action_frames.items() if not frames]
        if empty_actions:
            logger.error("[Stage 4] 以下动作抽帧为空，已从下游阶段移除: %s", empty_actions)
            for name in empty_actions:
                del action_frames[name]
        if not action_frames:
            raise RuntimeError("所有动作抽帧均为空，管线终止")
        logger.info("[Stage 3/4] Extracted frames for %d actions", len(action_frames))

        # ─── Stage 5: 去背景 ─────────────────────────────────────────────
        t5 = time.time()
        logger.info("[Stage 5] 开始: 去背景 (%d 个动作)", len(action_frames))
        action_frames_nobg = self._stage_remove_bg(action_frames, dirs["nobg"])
        self._stage_times["Stage 5 去背景"] = time.time() - t5
        logger.info(
            "[Stage 5] 完成: %d 个动作, 耗时 %.1fs",
            len(action_frames_nobg),
            self._stage_times["Stage 5 去背景"],
        )

        # ─── Stage 6: Sprite 打包 ────────────────────────────────────────
        t6 = time.time()
        logger.info("[Stage 6] 开始: Sprite 打包")
        manifest_path = self._stage_pack(action_frames_nobg, actions, dirs["sprites"], body_type)
        self._stage_times["Stage 6 Sprite打包"] = time.time() - t6
        logger.info(
            "[Stage 6] 完成: %s, 耗时 %.1fs",
            manifest_path,
            self._stage_times["Stage 6 Sprite打包"],
        )

        # ─── Stage 7: Rust 项目生成 + 编译 ───────────────────────────────
        t7 = time.time()
        logger.info("[Stage 7] 开始: Rust 项目生成 + 编译")
        result = self._stage_runtime(dirs["sprites"], manifest_path)
        self._stage_times["Stage 7 运行时生成"] = time.time() - t7
        logger.info("[Stage 7] 完成: 耗时 %.1fs", self._stage_times["Stage 7 运行时生成"])

        elapsed = time.time() - start_time
        self._log_stage_times()
        logger.info("=" * 60)
        logger.info("Pipeline completed in %.1fs", elapsed)
        logger.info("Output: %s", result)
        logger.info("=" * 60)

        return result

    # ─── Stage 实现 ───────────────────────────────────────────────────────

    def _stage_classify(self, input_image: Path, output_dir: Path):
        """Stage 0: 体型分类。"""
        from pet_generator.stages.classifier import ClassificationResult, Classifier

        if self.settings.body_type_override:
            logger.info(
                "Body type override: %s (skipping AI classification)",
                self.settings.body_type_override,
            )
            return ClassificationResult.default(self.settings.body_type_override)

        from pet_generator.providers import create_vision_provider

        vision = create_vision_provider(self.settings.classifier)
        classifier = Classifier(vision)
        return classifier.run(input_image, output_dir)

    def _stage_standardize(self, input_image: Path, classification, output_dir: Path) -> Path:
        """Stage 1: 图像标准化。"""
        from pet_generator.providers import create_image_provider
        from pet_generator.stages.standardizer import Standardizer

        image_provider = create_image_provider(
            self.settings.providers.image_provider, self.settings.providers
        )
        standardizer = Standardizer(image_provider)
        return standardizer.run(input_image, classification, output_dir)

    def _stage_poses(
        self, standard_image: Path, actions, body_type: str, output_dir: Path
    ) -> dict[str, Path]:
        """Stage 2: 尾帧/姿态生成（带产物缓存，命中则跳过图像生成 API）。

        缓存判据：最终产物 ``output_dir/{action.name}.png`` 存在即命中。
        该文件名约定与并发版 PoseGenerator（每动作临时子目录 + 原子重命名
        到 ``{action.name}.png``）兼容；缓存检查不依赖任何临时文件。
        """
        from pet_generator.stages.pose_generator import PoseGenerator

        pose_images: dict[str, Path] = {}
        missing_actions = []
        for action in actions:
            cached = output_dir / f"{action.name}.png"
            if cached.exists():
                logger.info("[Stage 2] 缓存命中: %s (跳过图像生成 API)", action.name)
                pose_images[action.name] = cached
            else:
                missing_actions.append(action)

        if missing_actions:
            from pet_generator.providers import create_image_provider

            image_provider = create_image_provider(
                self.settings.providers.image_provider, self.settings.providers
            )
            pose_gen = PoseGenerator(image_provider)
            generated = pose_gen.run(standard_image, missing_actions, body_type, output_dir)
            pose_images.update(generated)
        else:
            logger.info("[Stage 2] 全部姿态图缓存命中，跳过 API 调用")

        return pose_images

    def _stage_video_and_frames(
        self,
        standard_image: Path,
        pose_images: dict[str, Path],
        actions,
        dirs: dict[str, Path],
    ) -> dict[str, list[Path]]:
        """Stage 3 & 4: 视频生成 + 帧提取（或 skip-video fallback）。

        两个阶段均带产物缓存：
        - Stage 3: ``videos/{action.name}.mp4`` 存在且 >100KB 则跳过视频 API。
        - Stage 4: ``frames/{action.name}/frame_*.png`` 数量达到预期 80% 则跳过 ffmpeg。
        """
        if self.settings.pipeline.skip_video:
            logger.info("[Stage 3] SKIP_VIDEO mode: using [standard, pose] as 2-frame fallback")
            action_frames: dict[str, list[Path]] = {}
            for action in actions:
                if action.name in pose_images:
                    action_frames[action.name] = [standard_image, pose_images[action.name]]
            return action_frames

        # ─── Stage 3: 视频生成（带产物缓存）──────────────────────────────
        from pet_generator.stages.video_generator import VideoGenerator

        t3 = time.time()
        logger.info("[Stage 3] 开始: 视频生成 (%d 个动作)", len(actions))
        videos: dict[str, Path] = {}
        missing_video_actions = []
        for action in actions:
            cached = dirs["videos"] / f"{action.name}.mp4"
            if cached.exists() and cached.stat().st_size > 100_000:
                logger.info("[Stage 3] 缓存命中: %s (跳过视频生成 API)", action.name)
                videos[action.name] = cached
            else:
                missing_video_actions.append(action)

        if missing_video_actions:
            from pet_generator.providers import create_video_provider

            video_provider = create_video_provider(
                self.settings.providers.video_provider, self.settings.providers
            )
            video_gen = VideoGenerator(video_provider)
            generated = video_gen.run(
                standard_image, pose_images, missing_video_actions, dirs["videos"]
            )
            videos.update(generated)
        else:
            logger.info("[Stage 3] 全部视频缓存命中，跳过 API 调用")

        self._stage_times["Stage 3 视频生成"] = time.time() - t3
        logger.info(
            "[Stage 3] 完成: %d 个视频, 耗时 %.1fs",
            len(videos),
            self._stage_times["Stage 3 视频生成"],
        )

        # ─── Stage 4: 帧提取（带产物缓存）────────────────────────────────
        from pet_generator.stages.frame_extractor import FrameExtractor

        t4 = time.time()
        logger.info("[Stage 4] 开始: ffmpeg 抽帧 (%d 个视频)", len(videos))
        extractor = FrameExtractor()
        action_frames = {}
        for action in actions:
            frame_dir = dirs["frames"] / action.name
            existing = sorted(frame_dir.glob("frame_*.png")) if frame_dir.exists() else []
            expected = int(action.duration_secs * action.fps)
            threshold = max(1, int(expected * 0.8))
            if len(existing) >= threshold:
                logger.info(
                    "[Stage 4] 缓存命中: %s (%d 帧, 跳过 ffmpeg)",
                    action.name,
                    len(existing),
                )
                action_frames[action.name] = existing
                continue

            if action.name in videos:
                frames = extractor.extract(
                    videos[action.name],
                    frame_dir,
                    fps=action.fps,
                    max_frames=int(action.duration_secs * action.fps) + 5,
                )
                action_frames[action.name] = frames
            else:
                logger.warning("[Stage 4] 动作 %s 无可用视频，帧列表为空", action.name)
                action_frames[action.name] = []

        self._stage_times["Stage 4 帧提取"] = time.time() - t4
        total_frames = sum(len(f) for f in action_frames.values())
        logger.info(
            "[Stage 4] 完成: %d 个动作, %d 帧, 耗时 %.1fs",
            len(action_frames),
            total_frames,
            self._stage_times["Stage 4 帧提取"],
        )

        return action_frames

    def _stage_remove_bg(
        self, action_frames: dict[str, list[Path]], output_dir: Path
    ) -> dict[str, list[Path]]:
        """Stage 5: 去背景。"""
        from pet_generator.stages.bg_remover import BackgroundRemover

        bg_remover = BackgroundRemover(model_type=self.settings.pipeline.bg_model)
        result: dict[str, list[Path]] = {}
        for name, frames in action_frames.items():
            result[name] = bg_remover.remove_batch(frames, output_dir / name)
        return result

    def _stage_pack(
        self,
        action_frames_nobg: dict[str, list[Path]],
        actions,
        output_dir: Path,
        body_type: str = "humanoid",
    ) -> Path:
        """Stage 6: Sprite 打包。"""
        from pet_generator.stages.sprite_packer import SpritePacker

        packer = SpritePacker(frame_size=self.settings.pipeline.frame_size)
        return packer.pack_all(
            action_frames_nobg,
            output_dir,
            actions,
            pet_name=self.settings.pet_name,
            body_type=body_type,
        )

    def _stage_runtime(self, sprite_dir: Path, manifest_path: Path) -> Path:
        """Stage 7: Rust 项目生成 + 可选编译。"""
        from pet_generator.runtime_gen import RuntimeGenerator

        runtime_gen = RuntimeGenerator(self.settings)
        project_dir = runtime_gen.generate(sprite_dir, manifest_path)

        if self.settings.pipeline.no_compile:
            logger.info("[Stage 7] NO_COMPILE mode: project generated at %s", project_dir)
            return project_dir

        from pet_generator.runtime_gen.compiler import compile_project

        binary = compile_project(
            project_dir,
            release=not self.settings.pipeline.debug_build,
            verbose=self.settings.pipeline.verbose,
        )
        logger.info("[Stage 7] Compiled binary: %s", binary)
        return binary

    # ─── 辅助方法 ─────────────────────────────────────────────────────────

    def _log_stage_times(self) -> None:
        """打印各阶段耗时汇总，便于定位性能瓶颈。"""
        logger.info("=" * 50)
        logger.info("各阶段耗时汇总:")
        for name, elapsed in self._stage_times.items():
            logger.info("  %-22s: %.1fs", name, elapsed)
        logger.info("=" * 50)

    def _setup_output_dirs(self) -> dict[str, Path]:
        """创建输出子目录结构（带序号前缀，便于调试）。"""
        base = Path(self.settings.pipeline.output_dir)
        dirs = {
            "classification": base / "00_classification",
            "standard": base / "01_standard",
            "poses": base / "02_poses",
            "videos": base / "03_videos",
            "frames": base / "04_frames",
            "nobg": base / "05_nobg",
            "sprites": base / "06_sprites",
        }
        for d in dirs.values():
            d.mkdir(parents=True, exist_ok=True)
        return dirs
