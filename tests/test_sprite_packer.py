"""Stage 6 打包边界 — 帧数、尺寸、模式、损坏帧、空动作。

全部用合成素材（`tests/support/synth.py`），刻意造真实素材不会出现的边界形态。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from pet_generator.config.actions.base import ActionDef
from pet_generator.stages.sprite_packer import SpritePacker
from tests.support import synth


def _action(name: str, *, fps: int = 12, loop: bool = True, duration: float = 2.0) -> ActionDef:
    return ActionDef(
        name=name,
        description=f"{name} desc",
        pose_prompt=f"{name} pose",
        video_prompt=f"{name} motion",
        fps=fps,
        loop=loop,
        duration_secs=duration,
    )


@pytest.mark.parametrize("frame_count", [1, 2, 7])
def test_sheet_width_scales_with_frame_count(tmp_path: Path, frame_count: int):
    """单帧与多帧都必须满足 宽度 == frame_size × 帧数。"""
    frames = synth.make_frames(tmp_path / "src", frame_count)
    sheet = SpritePacker(frame_size=128).pack_single(frames, tmp_path / "out.png")
    with Image.open(sheet) as img:
        assert img.size == (128 * frame_count, 128)


@pytest.mark.parametrize("size", [(300, 240), (101, 97), (1024, 1024)])
def test_non_square_and_odd_frames_are_normalized(tmp_path: Path, size):
    """非正方、奇数尺寸的输入帧都被归一化到 frame_size 正方形。"""
    frames = synth.make_frames(tmp_path / "src", 2, size=size)
    sheet = SpritePacker(frame_size=64).pack_single(frames, tmp_path / "out.png")
    with Image.open(sheet) as img:
        assert img.size == (128, 64)
        assert img.mode == "RGBA"


def test_rgb_input_becomes_rgba(tmp_path: Path):
    """RGB 输入（Stage 5 之前的真实形态）必须转成 RGBA，否则透明背景会丢失。"""
    frames = synth.make_frames(tmp_path / "src", 2, mode="RGB")
    sheet = SpritePacker(frame_size=32).pack_single(frames, tmp_path / "out.png")
    with Image.open(sheet) as img:
        assert img.mode == "RGBA"


def test_corrupt_frame_becomes_transparent_slot(tmp_path: Path):
    """损坏帧不应中断打包，对应槽位留空（宽度仍与帧数一致）。"""
    frames = synth.make_frames(tmp_path / "src", 3, size=(64, 64))
    frames[1].write_bytes(b"not a png")
    sheet = SpritePacker(frame_size=64).pack_single(frames, tmp_path / "out.png")
    with Image.open(sheet) as img:
        assert img.size == (192, 64)
        # 中间槽位应完全透明
        middle = img.crop((64, 0, 128, 64))
        assert middle.getextrema()[3] == (0, 0)


def test_pack_all_skips_empty_actions_and_keeps_others(tmp_path: Path):
    """空帧动作被跳过且不进 manifest，其他动作正常打包。"""
    frames = synth.make_action_frames(tmp_path / "src", {"idle": 2, "wave": 3})
    frames["broken"] = []
    manifest_path = SpritePacker(frame_size=64).pack_all(
        frames,
        tmp_path / "sprites",
        [_action("idle"), _action("wave", loop=False)],
        pet_name="EdgePet",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(manifest["actions"]) == {"idle", "wave"}
    assert not (tmp_path / "sprites" / "broken_sheet.png").exists()


def test_manifest_carries_action_metadata(tmp_path: Path):
    """manifest 必须携带运行时契约需要的 5 元组来源字段。"""
    frames = synth.make_action_frames(tmp_path / "src", {"dance": 4})
    manifest_path = SpritePacker(frame_size=64).pack_all(
        frames,
        tmp_path / "sprites",
        [_action("dance", fps=24, loop=True, duration=1.5)],
        pet_name="MetaPet",
        body_type="quadruped",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["pet_name"] == "MetaPet"
    assert manifest["body_type"] == "quadruped"
    assert manifest["frame_size"] == 64
    entry = manifest["actions"]["dance"]
    assert entry == {
        "file": "dance_sheet.png",
        "frame_count": 4,
        "fps": 24,
        "loop": True,
        "duration_secs": 1.5,
    }


def test_unknown_action_falls_back_to_frame_derived_duration(tmp_path: Path):
    """manifest 里出现动作集之外的动作时，用帧数/fps 推导时长而不是崩溃。"""
    frames = synth.make_action_frames(tmp_path / "src", {"mystery": 6})
    manifest_path = SpritePacker(frame_size=32).pack_all(frames, tmp_path / "sprites", [])
    entry = json.loads(manifest_path.read_text(encoding="utf-8"))["actions"]["mystery"]
    assert entry["fps"] == 12
    assert entry["duration_secs"] == pytest.approx(0.5)  # 6 帧 / 12 fps


def test_width_selfcheck_rejects_tampered_sheet(tmp_path: Path):
    """宽度自检必须拦住「sheet 与 frame_count 不符」的产物（防错乱动画）。"""
    packer = SpritePacker(frame_size=256)
    bad = tmp_path / "bad_sheet.png"
    Image.new("RGBA", (300, 256), (0, 0, 0, 0)).save(bad, format="PNG")
    with pytest.raises(RuntimeError, match="frame_count"):
        packer._verify_sheet_width("idle", bad, frame_count=2)
