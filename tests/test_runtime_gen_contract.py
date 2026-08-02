"""生成契约回归测试 — 数据驱动 + fail-fast + 守护。

覆盖的缺陷路径：
- frame_size 在生成器与运行时之间不同步 → test_patch_frame_size_512
- 闭合的 Rust 枚举 vs 开放的动作配置之间的隐性耦合
  → test_whitelist_failfast / test_all_body_type_variants_known
- patch 正则与常量声明逐字符强耦合（模板一改就静默失配）
  → test_patch_sprite_sheets_5tuple（断言 count==1 且锁定注释保留）
- frame_count 与 sheet 宽度缺一致性校验 → test_frame_count_mismatch

设计：纯单元 / fixture 级，不依赖真实图像生成，也不依赖 R1 的实时模板进度——
模板文本用契约 docs/standards/GENERATOR_RUNTIME_CONTRACT.md §1.2 / §2.1 的精确字符串 fixture 自测。

运行: pytest tests/test_runtime_gen_contract.py -v
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from PIL import Image

from pet_generator.config import Settings
from pet_generator.config.actions import get_actions, get_all_body_types
from pet_generator.runtime_gen import KNOWN_ANIM_STATES, resolve_rust_variant
from pet_generator.runtime_gen.rust_project import RuntimeGenerator
from pet_generator.stages.sprite_packer import SpritePacker

# ---------------------------------------------------------------------------
# 契约 fixture：逐字摘自 docs/standards/GENERATOR_RUNTIME_CONTRACT.md §1.2 / §2.1（R1 必须产出的文本）
# ---------------------------------------------------------------------------

# §1.2 模板 main.rs 中 SPRITE_SHEETS 的精确声明文本
TEMPLATE_SPRITE_SHEETS = (
    "// GENERATOR-CONTRACT: DO NOT EDIT — kept in sync by pet_generator/runtime_gen/rust_project.py\n"
    "const SPRITE_SHEETS: &[(AnimState, &[u8], f32, bool, f32)] = &[\n"
    "    // Generator will insert entries here\n"
    "];"
)

# §2.1 模板 main.rs 中 FRAME_SIZE 的精确声明文本
TEMPLATE_FRAME_SIZE = (
    "// GENERATOR-CONTRACT: DO NOT EDIT — patched from manifest.frame_size by the generator\n"
    "const FRAME_SIZE: u32 = 256;"
)

# 组合成一个最小 main.rs fixture（含两处锁定声明 + 一段干扰 doc-comment 示例，
# 用以验证正则只锚定锁定注释行、不误伤 doc-comment 中的 5 元组示例）
TEMPLATE_MAIN_RS = (
    "//! Desktop pet runtime.\n"
    "/// doc-comment 示例（不应被 patch 误伤）：\n"
    "/// const SPRITE_SHEETS: &[(AnimState, &[u8], f32, bool, f32)] = &[\n"
    '///     (AnimState::Idle, include_bytes!("../assets/idle.png"), 8.0, true, 3.0),\n'
    "/// ];\n"
    "\n"
    f"{TEMPLATE_FRAME_SIZE}\n"
    "\n"
    f"{TEMPLATE_SPRITE_SHEETS}\n"
)


def _make_generator() -> RuntimeGenerator:
    """构造一个 RuntimeGenerator（单元测试不触网、不读模板目录）。"""
    return RuntimeGenerator(Settings(pet_name="ContractTestPet"))


# ---------------------------------------------------------------------------
# SPRITE_SHEETS 5 元组 patch（断言 count==1 + 锁定注释保留）
# ---------------------------------------------------------------------------


def test_patch_sprite_sheets_5tuple():
    gen = _make_generator()
    manifest = {
        "body_type": "humanoid",
        "actions": {
            "idle": {
                "file": "idle_sheet.png",
                "fps": 12,
                "loop": True,
                "frame_count": 36,
                "duration_secs": 3.0,
            },
            "wave": {
                "file": "wave_sheet.png",
                "fps": 12,
                "loop": False,
                "frame_count": 24,
                "duration_secs": 2.0,
            },
        },
    }

    entries = gen._build_sprite_entries(manifest)
    assert len(entries) == 2

    # 契约 §1.5 正则必须对 §1.2 模板恰好匹配 1 次（守护「模板一改就静默失配」）
    pattern = (
        r"// GENERATOR-CONTRACT: DO NOT EDIT[^\n]*\n"
        r"const SPRITE_SHEETS: &\[\(AnimState, &\[u8\], f32, bool, f32\)\] = &\[.*?\];"
    )
    _matches, count = re.subn(pattern, "X", TEMPLATE_MAIN_RS, flags=re.DOTALL | re.MULTILINE)
    assert count == 1, f"SPRITE_SHEETS 正则应恰好匹配 1 次，实际 {count}"

    # 经生成器 patch 后：含 5 元组条目 + 保留锁定注释行
    patched = gen._patch_sprite_sheets(TEMPLATE_MAIN_RS, entries)
    lock_line = (
        "// GENERATOR-CONTRACT: DO NOT EDIT — kept in sync by "
        "pet_generator/runtime_gen/rust_project.py"
    )
    assert lock_line in patched
    # 5 元组：(AnimState, include_bytes, fps, loop, duration_secs)
    assert (
        '(AnimState::Idle, include_bytes!("../assets/idle_sheet.png"), 12.0, true, 3.0),' in patched
    )
    assert (
        '(AnimState::Wave, include_bytes!("../assets/wave_sheet.png"), 12.0, false, 2.0),'
        in patched
    )
    # 占位注释被替换掉
    assert "// Generator will insert entries here" not in patched
    # doc-comment 示例未被误伤（仍保留在文件中）
    assert "/// const SPRITE_SHEETS" in patched


def test_duration_secs_fallback_from_frame_count():
    """duration_secs 缺失时用 frame_count/fps 兜底（保留 2 位小数）。"""
    gen = _make_generator()
    manifest = {
        "body_type": "quadruped",
        "actions": {
            # 无 duration_secs：frame_count=18, fps=12 → 1.5s
            "walk": {"file": "walk_sheet.png", "fps": 12, "loop": True, "frame_count": 18},
        },
    }
    entries = gen._build_sprite_entries(manifest)
    assert entries == [
        '    (AnimState::Walk, include_bytes!("../assets/walk_sheet.png"), 12.0, true, 1.5),'
    ]


# ---------------------------------------------------------------------------
# FRAME_SIZE patch（--frame-size 512）
# ---------------------------------------------------------------------------


def test_patch_frame_size_512():
    gen = _make_generator()
    manifest = {"frame_size": 512, "actions": {}}

    patched = gen._patch_frame_size(TEMPLATE_MAIN_RS, manifest)
    assert "const FRAME_SIZE: u32 = 512;" in patched
    # 锁定注释保留
    assert (
        "// GENERATOR-CONTRACT: DO NOT EDIT — patched from manifest.frame_size by the generator"
        in patched
    )
    # 原 256 已被替换
    assert "const FRAME_SIZE: u32 = 256;" not in patched


def test_patch_frame_size_missing_keeps_default():
    """manifest 无 frame_size → 不改动（向后兼容，保留模板默认 256）。"""
    gen = _make_generator()
    patched = gen._patch_frame_size(TEMPLATE_MAIN_RS, {"actions": {}})
    assert "const FRAME_SIZE: u32 = 256;" in patched


def test_patch_frame_size_count_must_be_one():
    """锁定声明缺失时 fail-fast（count != 1 → RuntimeError）。"""
    gen = _make_generator()
    broken = "const FRAME_SIZE: u32 = 256;\n"  # 缺锁定注释 → 正则不匹配
    with pytest.raises(RuntimeError, match="FRAME_SIZE"):
        gen._patch_frame_size(broken, {"frame_size": 512})


# ---------------------------------------------------------------------------
# AnimState 白名单 fail-fast
# ---------------------------------------------------------------------------


def test_whitelist_failfast():
    """含未注册 variant 的 manifest → 生成 5 元组条目时编译前 fail-fast。"""
    gen = _make_generator()
    manifest = {
        "body_type": "humanoid",
        "actions": {
            # snake_to_pascal("fly_away") = "FlyAway"，不在 KNOWN_ANIM_STATES
            "fly_away": {"file": "fly_away_sheet.png", "fps": 12, "loop": True, "frame_count": 12},
        },
    }
    with pytest.raises(ValueError) as exc_info:
        gen._build_sprite_entries(manifest)
    msg = str(exc_info.value)
    assert "FlyAway" in msg
    assert "fly_away" in msg
    assert "humanoid" in msg


def test_whitelist_validator_direct():
    """validate_rust_variant 对合法/非法变体的行为。"""
    from pet_generator.runtime_gen import validate_rust_variant

    # 合法：不抛
    validate_rust_variant("Idle", "idle", "humanoid")
    # 非法：抛清晰错误
    with pytest.raises(ValueError, match="NotARealState"):
        validate_rust_variant("NotARealState", "bogus", "object")


def test_all_body_type_variants_known():
    """遍历 4 套动作集，断言每个 rust_variant ∈ KNOWN_ANIM_STATES。"""
    assert len(KNOWN_ANIM_STATES) == 29, "白名单应为契约 §3 的 29 个变体"
    assert set(get_all_body_types()) == {"humanoid", "quadruped", "limbless", "object"}

    for body_type in get_all_body_types():
        for action in get_actions(body_type):
            variant = resolve_rust_variant(action.name, action.rust_variant or None)
            assert variant in KNOWN_ANIM_STATES, (
                f"body_type='{body_type}' action='{action.name}' "
                f"rust_variant='{variant}' 不在 KNOWN_ANIM_STATES 白名单中"
            )


# ---------------------------------------------------------------------------
# frame_count 与 sheet 宽度一致性自检
# ---------------------------------------------------------------------------


def test_frame_count_mismatch(tmp_path: Path):
    """构造 sheet 宽度与 frame_count 不符 → 打包器报错。"""
    packer = SpritePacker(frame_size=256)

    # 造一张宽度 300px 的“坏” sheet（既不等于 256*1 也不等于 256*2）
    bad_sheet = tmp_path / "bad_sheet.png"
    Image.new("RGBA", (300, 256), (0, 0, 0, 0)).save(bad_sheet, format="PNG")

    with pytest.raises(RuntimeError) as exc_info:
        packer._verify_sheet_width("idle", bad_sheet, frame_count=2)
    msg = str(exc_info.value)
    assert "idle" in msg
    assert "frame_count" in msg


def test_frame_count_match_passes(tmp_path: Path):
    """宽度 == frame_size * frame_count 时自检通过（不抛）。"""
    packer = SpritePacker(frame_size=256)
    good_sheet = tmp_path / "good_sheet.png"
    Image.new("RGBA", (256 * 3, 256), (0, 0, 0, 0)).save(good_sheet, format="PNG")
    # 不抛即通过
    packer._verify_sheet_width("walk", good_sheet, frame_count=3)


def test_pack_all_end_to_end_selfcheck(tmp_path: Path):
    """pack_all 真实打包后自检通过，且 manifest 含 frame_size/frame_count/duration_secs。"""
    import json

    from pet_generator.config.actions.base import ActionDef

    packer = SpritePacker(frame_size=128)
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    # 造 3 帧任意尺寸 PNG（pack_single 会 resize 到 128）
    frame_paths = []
    for i in range(3):
        p = frames_dir / f"f{i}.png"
        Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(p, format="PNG")
        frame_paths.append(p)

    actions = [
        ActionDef(
            name="idle",
            description="待机",
            pose_prompt="pose",
            video_prompt="video",
            duration_secs=3.0,
            fps=12,
            loop=True,
        )
    ]
    out_dir = tmp_path / "out"
    manifest_path = packer.pack_all(
        {"idle": frame_paths}, out_dir, actions, pet_name="T", body_type="humanoid"
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["frame_size"] == 128
    assert manifest["actions"]["idle"]["frame_count"] == 3
    assert manifest["actions"]["idle"]["duration_secs"] == 3.0
    # sheet 宽度确实 == 128 * 3
    with Image.open(out_dir / "idle_sheet.png") as img:
        assert img.size[0] == 128 * 3


# ---------------------------------------------------------------------------
# 真实模板端到端：守护「模板重构 ↔ patch 正则 ↔ 模块化目录」三者一致
# ---------------------------------------------------------------------------


def test_generate_from_real_template(tmp_path: Path):
    """用真实 pet-runtime 模板生成项目，断言 patch 命中且模块化目录完整复制。

    这是模板重构的守护网：契约正则只锚定 main.rs 的两处锁定声明，
    但生成器还依赖「模板目录可整体复制」这一隐式契约（含 src/ui/ 子模块）。
    """
    settings = Settings(pet_name="TemplatePet")
    settings.pipeline.output_dir = str(tmp_path / "out")

    generator = RuntimeGenerator(settings)
    assert generator.template_dir.exists(), "模板目录必须存在"

    # 造两张符合 frame_size 的 sheet + manifest（不触网、不依赖真实素材）
    sprite_dir = tmp_path / "sprites"
    sprite_dir.mkdir()
    frame_size = 128
    Image.new("RGBA", (frame_size * 3, frame_size), (255, 0, 0, 255)).save(
        sprite_dir / "idle_sheet.png", format="PNG"
    )
    Image.new("RGBA", (frame_size * 2, frame_size), (0, 255, 0, 255)).save(
        sprite_dir / "wave_sheet.png", format="PNG"
    )
    manifest = {
        "pet_name": "TemplatePet",
        "body_type": "humanoid",
        "frame_size": frame_size,
        "actions": {
            "idle": {
                "file": "idle_sheet.png",
                "frame_count": 3,
                "fps": 12,
                "loop": True,
                "duration_secs": 3.0,
            },
            "wave": {
                "file": "wave_sheet.png",
                "frame_count": 2,
                "fps": 12,
                "loop": False,
                "duration_secs": 2.0,
            },
        },
    }
    manifest_path = sprite_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    project_dir = generator.generate(sprite_dir, manifest_path)

    # 1) SPRITE_SHEETS / FRAME_SIZE patch 命中真实模板
    main_rs = (project_dir / "src" / "main.rs").read_text(encoding="utf-8")
    assert (
        '(AnimState::Idle, include_bytes!("../assets/idle_sheet.png"), 12.0, true, 3.0),' in main_rs
    )
    assert (
        '(AnimState::Wave, include_bytes!("../assets/wave_sheet.png"), 12.0, false, 2.0),'
        in main_rs
    )
    assert f"const FRAME_SIZE: u32 = {frame_size};" in main_rs
    assert "// Generator will insert entries here" not in main_rs

    # 2) 模块化目录完整复制（含 src/ui/ 子模块）
    for module in (
        "config.rs",
        "command.rs",
        "window.rs",
        "animation.rs",
        "behavior.rs",
        "interaction.rs",
        "pet.rs",
        "achievements.rs",
        "tray.rs",
        "ui/mod.rs",
        "ui/theme.rs",
        "ui/icons.rs",
        "ui/menu.rs",
        "ui/hud.rs",
        "ui/toast.rs",
    ):
        assert (project_dir / "src" / module).exists(), f"缺少模板模块 {module}"

    # 3) 包名改写 + 资产与 manifest 就位
    cargo_toml = (project_dir / "Cargo.toml").read_text(encoding="utf-8")
    assert 'name = "TemplatePet"' in cargo_toml
    assert (project_dir / "assets" / "idle_sheet.png").exists()
    assert (project_dir / "assets" / "fallback.png").exists()
    assert (project_dir / "manifest.json").exists()


def test_template_ui_text_is_ascii_only(template_dir: Path):
    """模板 UI 文案必须是纯 ASCII —— Bevy 内嵌默认字体只覆盖 U+0020..U+007E。

    非 ASCII 字符（emoji / ✕ / •）会渲染成 tofu 方块，这是曾经的线上缺陷。
    只检查产品代码：注释与 `#[cfg(test)]` 之后的测试段允许出现说明性字符。
    """
    template_ui = template_dir / "src" / "ui"
    offenders: list[str] = []
    for path in sorted(template_ui.glob("*.rs")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#[cfg(test)]"):
                break  # 测试段之后不属于 UI 文案
            if stripped.startswith("//"):
                continue  # 注释可以解释非 ASCII 字符
            if not line.isascii():
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, "UI 代码含非 ASCII 字面量:\n" + "\n".join(offenders)


def test_fallback_uses_standard_image_from_sibling_dir(tmp_path: Path):
    """01_standard 与 06_sprites 同级时必须命中标准图作为 fallback。

    旧实现多退了一级目录（``sprite_dir.parent.parent``），在真实管线布局下
    永远命中不到，导致生成项目的降级路径显示模板占位图而不是宠物本身。
    """
    output = tmp_path / "output"
    sprite_dir = output / "06_sprites"
    standard_dir = output / "01_standard"
    sprite_dir.mkdir(parents=True)
    standard_dir.mkdir(parents=True)
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()

    # 标准化阶段的真实产物名（非约定名），只有"取最新 PNG"才能命中
    Image.new("RGBA", (64, 64), (7, 8, 9, 255)).save(
        standard_dir / "20260802_012948_edited_0.png", format="PNG"
    )

    _make_generator()._copy_fallback(sprite_dir, assets_dir)

    fallback = assets_dir / "fallback.png"
    assert fallback.exists(), "必须复制标准图为 fallback.png"
    with Image.open(fallback) as img:
        assert img.size == (64, 64)


def test_fallback_keeps_template_when_no_standard_image(tmp_path: Path):
    """找不到标准图时不得写出 fallback.png（保留模板自带的占位图）。"""
    sprite_dir = tmp_path / "output" / "06_sprites"
    sprite_dir.mkdir(parents=True)
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()

    _make_generator()._copy_fallback(sprite_dir, assets_dir)
    assert not (assets_dir / "fallback.png").exists()
