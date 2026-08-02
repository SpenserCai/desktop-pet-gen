"""Stage 6: Sprite 打包 — 将逐帧 PNG 打包为水平 Sprite Sheet + manifest.json。

将每个动作的去背景帧序列水平拼接为单张 Sprite Sheet PNG，
并生成 manifest.json 描述所有动作的元数据，供 Rust 运行时加载。

输出结构:
    output_dir/
    ├── idle_sheet.png
    ├── walk_sheet.png
    ├── ...
    └── manifest.json

错误处理:
- 某动作帧列表为空 → skip 该动作（warn），不阻塞其他动作。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PIL import Image

from pet_generator.config.actions.base import ActionDef

logger = logging.getLogger(__name__)


class SpritePacker:
    """Stage 6 — Sprite Sheet 打包。

    Args:
        frame_size: 每帧的统一尺寸（正方形，宽=高）。默认 256px。
    """

    def __init__(self, frame_size: int = 256) -> None:
        self._frame_size = frame_size

    # -- 公开接口 ----------------------------------------------------------

    def pack_all(
        self,
        action_frames: dict[str, list[Path]],
        output_dir: Path,
        actions: list[ActionDef],
        *,
        pet_name: str = "pet",
        body_type: str = "humanoid",
    ) -> Path:
        """将所有动作的帧打包为水平 Sprite Sheet + manifest.json。

        Args:
            action_frames: {action_name: [frame_path, ...]} 去背景后的帧。
            output_dir: 输出目录（不存在时自动创建）。
            actions: 动作定义列表（提供 fps / loop / duration 等元数据）。
            pet_name: 宠物名称（写入 manifest）。
            body_type: 体型（写入 manifest）。

        Returns:
            manifest.json 的路径。
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # 构建 action_name → ActionDef 的快速查找表
        action_map: dict[str, ActionDef] = {a.name: a for a in actions}

        manifest_actions: dict[str, dict] = {}

        for action_name, frames in action_frames.items():
            # 帧为空 → skip
            if not frames:
                logger.warning("动作 '%s' 帧列表为空，跳过打包", action_name)
                continue

            # 打包 sprite sheet
            sheet_filename = f"{action_name}_sheet.png"
            sheet_path = output_dir / sheet_filename
            self.pack_single(frames, sheet_path)

            # 一致性自检：sheet 宽度必须 == frame_size * frame_count。
            # pack_single 把每帧 resize 到 frame_size 并水平拼接，宽度应严格等于
            # frame_size * len(frames)；不符说明拼接/resize 逻辑被破坏，fail-fast。
            self._verify_sheet_width(action_name, sheet_path, len(frames))

            # 构建 manifest 条目
            action_def = action_map.get(action_name)
            fps = action_def.fps if action_def else 12
            loop = action_def.loop if action_def else True
            duration_secs = action_def.duration_secs if action_def else len(frames) / fps

            manifest_actions[action_name] = {
                "file": sheet_filename,
                "frame_count": len(frames),
                "fps": fps,
                "loop": loop,
                "duration_secs": round(duration_secs, 2),
            }
            logger.info("Sprite sheet 已打包: %s (%d 帧)", sheet_filename, len(frames))

        # 生成 manifest.json
        manifest = {
            "pet_name": pet_name,
            "body_type": body_type,
            "frame_size": self._frame_size,
            "actions": manifest_actions,
        }

        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Manifest 已生成: %s (%d 个动作)", manifest_path, len(manifest_actions))
        return manifest_path

    def _verify_sheet_width(self, action_name: str, sheet_path: Path, frame_count: int) -> None:
        """一致性自检：断言 sheet 宽度 // frame_size == frame_count。

        pack_single 将每帧 resize 到 ``frame_size`` 并水平拼接，故 sheet 宽度
        应严格等于 ``frame_size * frame_count``。任何偏差都意味着打包/resize 逻辑
        被破坏（或 frame_size 与 runtime 不同步），必须 fail-fast 而非产出错乱动画。

        Raises:
            RuntimeError: sheet 宽度与 frame_count * frame_size 不一致。
        """
        with Image.open(sheet_path) as sheet:
            width, _height = sheet.size

        expected_width = self._frame_size * frame_count
        actual_count = width // self._frame_size

        if width != expected_width or actual_count != frame_count:
            raise RuntimeError(
                f"Sprite sheet 一致性校验失败 (action='{action_name}'): "
                f"sheet 宽度 {width}px 与 frame_count 不符。\n"
                f"  frame_size = {self._frame_size}, frame_count = {frame_count}\n"
                f"  期望宽度 = {expected_width}px (= frame_size * frame_count)\n"
                f"  实际宽度 = {width}px (width // frame_size = {actual_count} 帧)\n"
                f"  sheet 路径 = {sheet_path}\n"
                "打包逻辑（pack_single 水平拼接）可能已被破坏，请检查。"
            )

    def pack_single(self, frames: list[Path], output_path: Path) -> Path:
        """将单个动作的帧列表打包为水平 Sprite Sheet。

        所有帧统一 resize 到 ``frame_size x frame_size``，
        水平拼接为一张 PNG。

        Args:
            frames: 帧文件路径列表（按播放顺序）。
            output_path: 输出 Sprite Sheet PNG 路径。

        Returns:
            输出路径（与 output_path 相同）。
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        size = self._frame_size
        count = len(frames)

        # 创建画布: 宽 = frame_size * count, 高 = frame_size
        sheet = Image.new("RGBA", (size * count, size), (0, 0, 0, 0))

        for i, frame_path in enumerate(frames):
            try:
                frame_img = Image.open(frame_path).convert("RGBA")
                frame_img = frame_img.resize((size, size), Image.LANCZOS)
                sheet.paste(frame_img, (i * size, 0))
            except Exception as exc:  # noqa: BLE001
                logger.warning("帧加载失败，使用透明占位: %s (%s)", frame_path, exc)
                # 保持该位置为透明（不 paste）

        sheet.save(output_path, format="PNG")
        return output_path
