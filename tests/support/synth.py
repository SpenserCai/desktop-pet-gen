"""合成素材工厂 — 程序化生成管线各阶段的输入/产物。

存在理由：绝大多数测试不需要真实 AI 素材，只需要「形状合法且刻意刁钻」的输入。
合成的边际成本是零，所以这里刻意生成比真实素材更难对付的形态：
非正方、奇数尺寸、alpha 边缘渐变、各动作帧数不等、单帧动作。

真实 AI 素材（`tests/fixtures/ai_pipeline/`）只用于「素材过管线」这一类回归，
两者分工见 `tests/fixtures/README.md`。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# 单帧 / 帧序列
# ---------------------------------------------------------------------------


def make_frame(
    path: Path,
    size: tuple[int, int] = (256, 256),
    *,
    mode: str = "RGBA",
    fill: tuple[int, int, int, int] = (220, 90, 120, 255),
    soft_edges: bool = True,
) -> Path:
    """生成一张单帧 PNG。

    Args:
        path: 目标文件路径（父目录自动创建）。
        size: (宽, 高)，允许非正方与奇数。
        mode: ``RGBA`` 或 ``RGB``（``RGB`` 模拟 Stage 5 之前的无 alpha 形态）。
        fill: 主体填充色。
        soft_edges: 是否在四周制造 alpha 渐变（仅 RGBA 生效），
            用于逼近真实抠图边缘，能暴露「按 alpha 裁剪/居中」的实现缺陷。

    Returns:
        写入的路径。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = size
    if mode == "RGB":
        img = Image.new("RGB", size, fill[:3])
        draw = ImageDraw.Draw(img)
        draw.ellipse((width * 0.2, height * 0.2, width * 0.8, height * 0.8), fill=(30, 30, 40))
        img.save(path, format="PNG")
        return path

    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 主体：椭圆（非满幅，保证四周有透明区域可供命中测试/裁剪逻辑发挥）
    draw.ellipse((width * 0.15, height * 0.1, width * 0.85, height * 0.95), fill=fill)
    if soft_edges:
        alpha = img.getchannel("A")
        # 沿边缘做一圈线性衰减，制造半透明像素
        px = alpha.load()
        band = max(1, min(width, height) // 32)
        for y in range(height):
            for x in range(width):
                if px[x, y] == 0:
                    continue
                edge = min(x, y, width - 1 - x, height - 1 - y)
                if edge < band:
                    px[x, y] = int(px[x, y] * (edge + 1) / (band + 1))
        img.putalpha(alpha)
    img.save(path, format="PNG")
    return path


def make_frames(
    out_dir: Path,
    count: int,
    *,
    size: tuple[int, int] = (256, 256),
    mode: str = "RGBA",
    prefix: str = "frame_",
) -> list[Path]:
    """生成一个动作的帧序列（文件名零填充，保证排序即播放顺序）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for i in range(count):
        # 逐帧变色，便于断言「帧未被错误复用」
        shade = 60 + int(160 * (i + 1) / count)
        frames.append(
            make_frame(
                out_dir / f"{prefix}{i:04d}.png",
                size=size,
                mode=mode,
                fill=(shade, 90, 200 - shade // 2, 255),
            )
        )
    return frames


def make_action_frames(
    root: Path,
    spec: dict[str, int] | None = None,
    *,
    size: tuple[int, int] = (256, 256),
    mode: str = "RGBA",
) -> dict[str, list[Path]]:
    """按 ``{动作名: 帧数}`` 生成多动作帧目录。

    默认 spec 刻意让帧数不等且包含单帧动作，用于暴露「假设各动作帧数相同」的缺陷。
    """
    spec = spec or {"idle": 3, "wave": 2, "yawn": 1}
    return {
        name: make_frames(root / name, count, size=size, mode=mode) for name, count in spec.items()
    }


# ---------------------------------------------------------------------------
# Sprite sheet / manifest
# ---------------------------------------------------------------------------


def make_sheet(path: Path, frame_size: int, frame_count: int, *, mode: str = "RGBA") -> Path:
    """生成一张横向拼接的 sheet（宽 = frame_size × frame_count）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new(mode, (frame_size * frame_count, frame_size), (0, 0, 0, 0)[: len(mode)])
    draw = ImageDraw.Draw(img)
    for i in range(frame_count):
        x0 = i * frame_size
        draw.ellipse(
            (x0 + frame_size * 0.1, frame_size * 0.1, x0 + frame_size * 0.9, frame_size * 0.9),
            fill=(200, 60 + i * 20, 90, 255)[: len(mode)],
        )
    img.save(path, format="PNG")
    return path


def make_sprite_dir(
    sprite_dir: Path,
    *,
    frame_size: int = 256,
    actions: dict[str, dict] | None = None,
    pet_name: str = "SynthPet",
    body_type: str = "humanoid",
) -> Path:
    """生成一套 sheet + manifest.json，返回 manifest 路径。

    ``actions`` 形如 ``{"idle": {"frame_count": 3, "fps": 12, "loop": True,
    "duration_secs": 3.0}}``；省略时用「循环 + 非循环」混合的默认集。
    """
    actions = actions or {
        "idle": {"frame_count": 3, "fps": 12, "loop": True, "duration_secs": 3.0},
        "wave": {"frame_count": 2, "fps": 12, "loop": False, "duration_secs": 2.0},
    }
    sprite_dir.mkdir(parents=True, exist_ok=True)
    manifest_actions: dict[str, dict] = {}
    for name, meta in actions.items():
        file_name = f"{name}_sheet.png"
        make_sheet(sprite_dir / file_name, frame_size, meta["frame_count"])
        manifest_actions[name] = {"file": file_name, **meta}

    manifest = {
        "pet_name": pet_name,
        "body_type": body_type,
        "frame_size": frame_size,
        "actions": manifest_actions,
    }
    manifest_path = sprite_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


# ---------------------------------------------------------------------------
# 真实素材落地（把录制夹具展开成逐动作帧目录）
# ---------------------------------------------------------------------------


def materialize_action_frames(
    ai_assets: Path,
    dest: Path,
    *,
    actions: list[str] | None = None,
) -> dict[str, list[Path]]:
    """把 `fixtures/ai_pipeline` 的录制素材展开为 ``{动作: [首帧, 尾帧]}``。

    真实管线在 ``skip_video`` 模式下正是用 ``[standard, pose]`` 作为 2 帧，
    所以这个函数复现的是**真实的 Stage 4 产物形态**，而不是测试专用的捏造结构。
    夹具本身保持只读——所有文件复制到 ``dest`` 后再交给被测代码。
    """
    poses_dir = ai_assets / "poses"
    standard = ai_assets / "standard.png"
    names = actions or sorted(p.stem for p in poses_dir.glob("*.png"))
    result: dict[str, list[Path]] = {}
    for name in names:
        action_dir = dest / name
        action_dir.mkdir(parents=True, exist_ok=True)
        first = action_dir / "frame_0000.png"
        last = action_dir / "frame_0001.png"
        shutil.copy(standard, first)
        shutil.copy(poses_dir / f"{name}.png", last)
        result[name] = [first, last]
    return result
