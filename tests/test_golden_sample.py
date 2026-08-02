"""真实 AI 素材过管线 — 黄金样本回归。

输入来自受版本控制的只读夹具 `tests/fixtures/ai_pipeline/`，产物写 `tmp_path`，
跑完即弃、仓库零残留；不依赖任何人工前置步骤。

覆盖两条真实路径：
1. **录制 sheet 直接生成**（frame_size=256）：录制的 10 张 sheet + manifest → Rust 项目。
2. **真实帧重打包**（frame_size=512）：真实 1024×1024 RGB 帧 → SpritePacker(512) → Rust 项目。

真实素材不可替代之处：1024×1024、**RGB 无 alpha**、主体不居中、AI 生成的边缘噪声。
合成素材（`tests/support/synth.py`）负责边界形态，两者互补。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from pet_generator.config import Settings
from pet_generator.config.actions import get_actions
from pet_generator.runtime_gen import RuntimeGenerator
from pet_generator.stages.sprite_packer import SpritePacker
from tests.support import rust_asserts, synth

pytestmark = pytest.mark.slow


def _generator(tmp_path: Path, pet_name: str) -> RuntimeGenerator:
    settings = Settings(pet_name=pet_name)
    settings.pipeline.output_dir = str(tmp_path / "out")
    settings.pipeline.no_compile = True
    return RuntimeGenerator(settings)


# ---------------------------------------------------------------------------
# 路径 1：录制 sheet → Rust 项目（frame_size=256）
# ---------------------------------------------------------------------------


def test_recorded_sheets_generate_project_256(ai_assets: Path, tmp_path: Path):
    """录制的真实 sheet + manifest 能生成完整项目，且 5 元组/FRAME_SIZE/无历史标记。"""
    sprite_dir = ai_assets / "sprites_256"
    manifest = json.loads((sprite_dir / "manifest.json").read_text(encoding="utf-8"))
    action_count = len(manifest["actions"])
    assert action_count == 10, "录制素材应覆盖 humanoid 完整 10 动作"

    project = _generator(tmp_path, "GoldenPet256").generate(
        sprite_dir, sprite_dir / "manifest.json"
    )
    main_rs = project / "src" / "main.rs"

    rust_asserts.assert_project_structure(project)
    rust_asserts.assert_frame_size(main_rs, 256)
    rust_asserts.assert_no_legacy_atlas_markers(main_rs)

    entries = rust_asserts.sprite_sheet_entries(main_rs)
    assert len(entries) == action_count, f"5 元组条目数 {len(entries)} != 动作数 {action_count}"

    # 每个条目都必须引用真实存在的 sheet 资产，且 fps/duration 与 manifest 一致
    by_asset = {Path(m["asset"]).name: m for m in entries}
    for name, meta in manifest["actions"].items():
        assert meta["file"] in by_asset, f"动作 {name} 未出现在 SPRITE_SHEETS"
        entry = by_asset[meta["file"]]
        assert (project / "assets" / meta["file"]).exists(), f"{meta['file']} 未复制到 assets/"
        assert float(entry["fps"]) == float(meta["fps"])
        assert (entry["loop"] == "true") == bool(meta["loop"])
        assert float(entry["duration"]) == pytest.approx(float(meta["duration_secs"]))

    idle = by_asset["idle_sheet.png"]
    assert idle["variant"] == "Idle", "idle_sheet.png 必须映射到 AnimState::Idle"


def test_recorded_sheets_are_rgba_and_width_consistent(ai_assets: Path):
    """录制 sheet 自身满足契约：RGBA、宽度 == frame_size × frame_count。"""
    sprite_dir = ai_assets / "sprites_256"
    manifest = json.loads((sprite_dir / "manifest.json").read_text(encoding="utf-8"))
    frame_size = manifest["frame_size"]
    for name, meta in manifest["actions"].items():
        with Image.open(sprite_dir / meta["file"]) as sheet:
            assert sheet.mode == "RGBA", f"{name} sheet 应为 RGBA（透明背景）"
            assert sheet.size == (frame_size * meta["frame_count"], frame_size), (
                f"{name} sheet 尺寸 {sheet.size} 与 frame_size×frame_count 不符"
            )


# ---------------------------------------------------------------------------
# 路径 2：真实帧 → SpritePacker(512) → Rust 项目
# ---------------------------------------------------------------------------


def test_real_frames_repack_512_end_to_end(ai_assets: Path, tmp_path: Path):
    """真实 1024×1024 RGB 帧经 SpritePacker(512) 重打包后可生成项目。

    这条路径同时验证：RGB→RGBA 转换、LANCZOS 缩放、宽度自检、
    manifest.frame_size 与 runtime `FRAME_SIZE` 的同步。
    """
    frames = synth.materialize_action_frames(ai_assets, tmp_path / "frames")
    assert len(frames) == 10
    # 真实素材在 Stage 5 之前是 RGB（无 alpha），这是合成素材造不出的形态
    with Image.open(frames["idle"][0]) as first:
        assert first.mode == "RGB"
        assert first.size == (1024, 1024)

    sprite_dir = tmp_path / "sprites_512"
    manifest_path = SpritePacker(frame_size=512).pack_all(
        frames, sprite_dir, get_actions("humanoid"), pet_name="GoldenPet512", body_type="humanoid"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["frame_size"] == 512

    for name, meta in manifest["actions"].items():
        with Image.open(sprite_dir / meta["file"]) as sheet:
            assert sheet.mode == "RGBA", f"{name}: 打包必须输出 RGBA"
            assert sheet.size == (512 * meta["frame_count"], 512)

    project = _generator(tmp_path, "GoldenPet512").generate(sprite_dir, manifest_path)
    main_rs = project / "src" / "main.rs"

    rust_asserts.assert_project_structure(project)
    rust_asserts.assert_frame_size(main_rs, 512)
    rust_asserts.assert_no_legacy_atlas_markers(main_rs)
    entries = rust_asserts.sprite_sheet_entries(main_rs)
    assert len(entries) == len(manifest["actions"])


def test_fallback_image_comes_from_real_standard(ai_assets: Path, tmp_path: Path):
    """`assets/fallback.png` 应取自同级 `01_standard/` 的真实标准图，而非模板占位图。

    守护一个已修复的缺陷：原实现多退一级目录查找，导致降级图永远是模板占位图。
    """
    sprite_dir = tmp_path / "run" / "06_sprites"
    standard_dir = tmp_path / "run" / "01_standard"
    standard_dir.mkdir(parents=True)
    # 用真实标准图，文件名保持管线的时间戳风格（不是写死的 standard.png）
    real_standard = standard_dir / "20260801_164236_edited_0.png"
    real_standard.write_bytes((ai_assets / "standard.png").read_bytes())

    manifest_path = synth.make_sprite_dir(sprite_dir, frame_size=256)
    project = _generator(tmp_path, "FallbackPet").generate(sprite_dir, manifest_path)

    fallback = project / "assets" / "fallback.png"
    assert fallback.exists()
    assert fallback.read_bytes() == real_standard.read_bytes(), (
        "fallback.png 应是同级 01_standard 的真实标准图"
    )
