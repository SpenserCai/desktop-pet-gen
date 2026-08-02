"""Rust 桌面宠物项目生成器。

从 pet-runtime 模板生成独立的 Rust 项目：
1. 复制模板源码与 Cargo.toml
2. 修改 package name 为宠物名称
3. 复制 sprite sheets 到 assets/
4. Patch main.rs 中的 SPRITE_SHEETS（5 元组）与 FRAME_SIZE 常量
5. 复制 manifest.json 供参考

契约（单一事实源）：docs/standards/GENERATOR_RUNTIME_CONTRACT.md
- §1.5 SPRITE_SHEETS patch 正则（锚定 GENERATOR-CONTRACT 锁定注释，count==1）
- §2.2 FRAME_SIZE patch 正则（与 manifest.frame_size 保持同步）
- §3 AnimState 白名单 KNOWN_ANIM_STATES（生成前 fail-fast，避免产出无法编译的代码）

设计取舍：
- 使用 shutil.copytree 复制模板，保证生成项目完全独立可编译。
- SPRITE_SHEETS / FRAME_SIZE patch 使用正则替换，以锁定注释锚定并断言 count==1，
  防止模板改动后正则静默失配。
- 不修改模板原文件，所有变更发生在生成的副本中。
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path

from pet_generator.config import Settings

logger = logging.getLogger(__name__)

# snake_case → PascalCase 映射表（覆盖所有已知 AnimState 变体）
ANIM_STATE_MAP: dict[str, str] = {
    "idle": "Idle",
    "happy": "Happy",
    "sleep": "Sleep",
    "drag": "Drag",
    "sleepy": "Sleepy",
    "hungry": "Hungry",
    "dance": "Dance",
    "wave": "Wave",
    "yawn": "Yawn",
    "stretch": "Stretch",
    "look_around": "LookAround",
    "tail_wag": "TailWag",
    "walk": "Walk",
    "run": "Run",
    "sit": "Sit",
    "pounce": "Pounce",
    "tilt_head": "TiltHead",
    "scratch": "Scratch",
    "bounce": "Bounce",
    "squish": "Squish",
    "stretch_vertical": "StretchVertical",
    "float": "Float",
    "spin": "Spin",
    "wobble": "Wobble",
    "glow": "Glow",
    "shake": "Shake",
    "tilt": "Tilt",
    "bounce_small": "BounceSmall",
    "sparkle": "Sparkle",
}

# AnimState 白名单（契约 GENERATOR_RUNTIME_CONTRACT.md §3，body-type-agnostic 全集，29 变体）。
# 生成前 fail-fast 校验：每个 action 解析出的 rust_variant 必须 ∈ 本集合，
# 否则在编译前抛出清晰错误（闭合的 Rust 枚举 vs 开放的动作配置之间的隐性耦合）。
# 注意：本集合是 runtime `animation.rs` 中 `AnimState` 枚举的镜像，
# 若 runtime 新增变体，必须同步更新此处（数据驱动的单一事实源）。
KNOWN_ANIM_STATES: frozenset[str] = frozenset(
    {
        "Idle",
        "Happy",
        "Sleep",
        "Drag",
        "Sleepy",
        "Hungry",
        "Dance",
        "Wave",
        "Yawn",
        "Stretch",
        "LookAround",
        "TailWag",
        "Walk",
        "Run",
        "Sit",
        "Pounce",
        "TiltHead",
        "Scratch",
        "Bounce",
        "Squish",
        "StretchVertical",
        "Float",
        "Spin",
        "Wobble",
        "Glow",
        "Shake",
        "Tilt",
        "BounceSmall",
        "Sparkle",
    }
)


def snake_to_pascal(name: str) -> str:
    """将 snake_case 转换为 PascalCase（通用 fallback）。"""
    return "".join(part.capitalize() for part in name.split("_") if part)


def resolve_rust_variant(action_name: str, explicit_variant: str | None = None) -> str:
    """解析动作名对应的 Rust AnimState 变体。

    优先级: explicit_variant > ANIM_STATE_MAP > snake_to_pascal 自动推导。
    """
    if explicit_variant:
        return explicit_variant
    if action_name in ANIM_STATE_MAP:
        return ANIM_STATE_MAP[action_name]
    return snake_to_pascal(action_name)


def validate_rust_variant(rust_variant: str, action_name: str, body_type: str = "unknown") -> None:
    """fail-fast 白名单校验：断言 rust_variant ∈ KNOWN_ANIM_STATES。

    在生成（编译）前阻断未注册的 AnimState 变体，避免把非法枚举写进
    main.rs 导致 Rust 编译失败。错误信息包含非法 variant 名 + action 名 +
    body_type，便于定位是哪个动作集引入了未注册变体。

    Raises:
        ValueError: rust_variant 不在白名单中。
    """
    if rust_variant not in KNOWN_ANIM_STATES:
        raise ValueError(
            f"Unknown AnimState variant '{rust_variant}' "
            f"(action='{action_name}', body_type='{body_type}').\n"
            f"Variant is not in KNOWN_ANIM_STATES whitelist. "
            f"If this is a new animation, add it to runtime `animation.rs::AnimState` "
            f"AND to KNOWN_ANIM_STATES in pet_generator/runtime_gen/rust_project.py.\n"
            f"Known variants ({len(KNOWN_ANIM_STATES)}): {sorted(KNOWN_ANIM_STATES)}"
        )


def _fmt_f32(value: float) -> str:
    """把浮点数格式化为 Rust f32 字面量（始终带小数点，最多 2 位）。

    例：3.0 -> "3.0"，2.5 -> "2.5"，1.333 -> "1.33"，12 -> "12.0"。
    """
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return text if "." in text else text + ".0"


class RuntimeGenerator:
    """从 pet-runtime 模板生成独立的 Rust 桌面宠物项目。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        # 模板目录：相对于本文件的 ../../pet-runtime
        self.template_dir = Path(__file__).resolve().parent.parent.parent / "pet-runtime"

    def generate(self, sprite_dir: Path, manifest_path: Path) -> Path:
        """生成独立的 Rust 桌面宠物项目。

        Args:
            sprite_dir: 包含 sprite sheet PNG 文件的目录。
            manifest_path: sprite packer 生成的 manifest.json 路径。

        Returns:
            生成的项目目录路径。

        Raises:
            FileNotFoundError: 模板目录或 manifest 不存在。
            RuntimeError: SPRITE_SHEETS patch 失败。
        """
        if not self.template_dir.exists():
            raise FileNotFoundError(
                f"Rust template directory not found: {self.template_dir}\n"
                "Ensure pet-runtime/ exists alongside pet_generator/."
            )
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")

        # 1. 创建项目目录
        project_dir = Path(self.settings.pipeline.output_dir) / self.settings.pet_name
        if project_dir.exists():
            logger.warning("Project directory exists, removing: %s", project_dir)
            shutil.rmtree(project_dir)

        logger.info("Generating Rust project: %s", project_dir)

        # 2. 复制模板（排除 target/ 和 .DS_Store）
        shutil.copytree(
            self.template_dir,
            project_dir,
            ignore=shutil.ignore_patterns("target", ".DS_Store", ".git"),
        )

        # 3. 修改 Cargo.toml 中的 package name
        self._patch_cargo_toml(project_dir)

        # 4. 复制 sprite sheets 到 assets/
        assets_dir = project_dir / "assets"
        assets_dir.mkdir(exist_ok=True)
        self._copy_sprites(sprite_dir, assets_dir)

        # 5. 复制标准图作为 fallback.png（如果存在）
        self._copy_fallback(sprite_dir, assets_dir)

        # 6. 读取 manifest 并 patch main.rs
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self._patch_main_rs(project_dir, manifest)

        # 7. 复制 manifest.json 到项目根目录（参考用）
        shutil.copy2(manifest_path, project_dir / "manifest.json")

        logger.info("Rust project generated successfully: %s", project_dir)
        return project_dir

    def _patch_cargo_toml(self, project_dir: Path) -> None:
        """修改 Cargo.toml 中的 package name 为宠物名称。"""
        cargo_toml = project_dir / "Cargo.toml"
        content = cargo_toml.read_text(encoding="utf-8")

        # 替换 name = "desktop-pet" → name = "<pet_name>"
        pet_name = self.settings.pet_name
        content = re.sub(
            r'^(name\s*=\s*)"[^"]*"',
            rf'\g<1>"{pet_name}"',
            content,
            count=1,
            flags=re.MULTILINE,
        )
        cargo_toml.write_text(content, encoding="utf-8")
        logger.debug("Patched Cargo.toml: package name → %s", pet_name)

    def _copy_sprites(self, sprite_dir: Path, assets_dir: Path) -> None:
        """复制所有 sprite sheet PNG 到 assets/ 目录。"""
        png_files = list(sprite_dir.glob("*.png"))
        if not png_files:
            logger.warning("No PNG files found in sprite dir: %s", sprite_dir)
            return

        for png in png_files:
            shutil.copy2(png, assets_dir / png.name)

        logger.info("Copied %d sprite sheets to assets/", len(png_files))

    def _copy_fallback(self, sprite_dir: Path, assets_dir: Path) -> None:
        """复制标准图作为 fallback.png（降级路径下宠物仍然是"它自己"）。

        查找顺序（先命中先用）：
        1. ``<sprite_dir>/../01_standard`` —— 管线真实布局（``output/06_sprites``
           与 ``output/01_standard`` 同级）；
        2. ``<sprite_dir>/../../01_standard`` —— 兼容更深一层的历史布局；
        3. ``<sprite_dir>/standard*.png``。

        每个候选目录内先找约定名（standard.png 等），再退化为"目录内最新的
        PNG"（标准化阶段的实际产物名形如 ``20260802_012948_edited_0.png``）。
        全部未命中时保留模板自带的 fallback.png 并 warning 提示。
        """
        searched: list[Path] = []
        for standard_dir in (
            sprite_dir.parent / "01_standard",
            sprite_dir.parent.parent / "01_standard",
        ):
            searched.append(standard_dir)
            candidate = self._pick_standard_image(standard_dir)
            if candidate is not None:
                shutil.copy2(candidate, assets_dir / "fallback.png")
                logger.info("Using standard image as fallback: %s", candidate)
                return

        # 也检查 sprite_dir 本身是否有 standard 图
        for candidate in sorted(sprite_dir.glob("standard*.png")):
            shutil.copy2(candidate, assets_dir / "fallback.png")
            logger.info("Using sprite dir standard image as fallback: %s", candidate)
            return

        # 找不到标准图时保留模板自带的 fallback.png。
        logger.warning(
            "No standard image found for fallback (searched %s and %s/standard*.png); "
            "keeping template fallback.png (opaque placeholder). "
            "The pet will render the placeholder silhouette if Idle sheet is missing/undecodable.",
            ", ".join(str(path) for path in searched),
            sprite_dir,
        )

    @staticmethod
    def _pick_standard_image(standard_dir: Path) -> Path | None:
        """在 01_standard 目录中挑一张标准图（约定名优先，否则取最新 PNG）。"""
        if not standard_dir.is_dir():
            return None
        for name in ("standard.png", "standard_image.png", "standardized.png"):
            candidate = standard_dir / name
            if candidate.exists():
                return candidate
        pngs = sorted(
            standard_dir.glob("*.png"), key=lambda path: path.stat().st_mtime, reverse=True
        )
        return pngs[0] if pngs else None

    def _patch_main_rs(self, project_dir: Path, manifest: dict) -> None:
        """Patch main.rs 中的 SPRITE_SHEETS（5 元组）与 FRAME_SIZE 常量。

        契约见 docs/standards/GENERATOR_RUNTIME_CONTRACT.md §1.5（SPRITE_SHEETS）与 §2.2（FRAME_SIZE）。
        两处 patch 均断言 ``re.subn`` 的 count == 1，否则抛 RuntimeError（
        patch 正则与常量声明逐字符强耦合，必须用锁定注释锚定并守护）。
        """
        main_rs = project_dir / "src" / "main.rs"
        content = main_rs.read_text(encoding="utf-8")

        # 从 manifest 构建条目（内含白名单 fail-fast 校验）
        entries = self._build_sprite_entries(manifest)

        if not entries:
            logger.warning("No sprite entries generated from manifest; SPRITE_SHEETS left empty.")
        else:
            content = self._patch_sprite_sheets(content, entries)

        # FRAME_SIZE patch（保持 frame_size 在生成器与运行时之间同步）
        content = self._patch_frame_size(content, manifest)

        main_rs.write_text(content, encoding="utf-8")

    def _patch_sprite_sheets(self, content: str, entries: list[str]) -> str:
        """用契约 §1.5 的正则替换 SPRITE_SHEETS 常量（保留锁定注释行）。"""
        entries_text = "\n".join(entries)
        replacement = (
            "// GENERATOR-CONTRACT: DO NOT EDIT — kept in sync by pet_generator/runtime_gen/rust_project.py\n"
            "const SPRITE_SHEETS: &[(AnimState, &[u8], f32, bool, f32)] = &[\n"
            f"{entries_text}\n"
            "];"
        )

        # 契约 §1.5：锚定锁定注释 + const 行（DOTALL | MULTILINE），count 必须 == 1。
        pattern = (
            r"// GENERATOR-CONTRACT: DO NOT EDIT[^\n]*\n"
            r"const SPRITE_SHEETS: &\[\(AnimState, &\[u8\], f32, bool, f32\)\] = &\[.*?\];"
        )
        new_content, count = re.subn(pattern, replacement, content, flags=re.DOTALL | re.MULTILINE)

        if count != 1:
            raise RuntimeError(
                f"Failed to patch SPRITE_SHEETS in main.rs: expected exactly 1 match, got {count}.\n"
                "The template must contain the locked declaration (GENERATOR_RUNTIME_CONTRACT.md §1.2):\n"
                "  // GENERATOR-CONTRACT: DO NOT EDIT — kept in sync by pet_generator/runtime_gen/rust_project.py\n"
                "  const SPRITE_SHEETS: &[(AnimState, &[u8], f32, bool, f32)] = &[ ... ];\n"
                "If the template changed, update the contract doc FIRST, then this regex."
            )

        logger.info("Patched SPRITE_SHEETS with %d entries.", len(entries))
        return new_content

    def _patch_frame_size(self, content: str, manifest: dict) -> str:
        """用契约 §2.2 的正则把 FRAME_SIZE 替换为 manifest.frame_size。

        若 manifest 无 ``frame_size`` 字段，默认 256 且不改动（向后兼容）。
        """
        frame_size = manifest.get("frame_size")
        if frame_size is None:
            logger.debug("manifest has no frame_size; keeping template FRAME_SIZE default.")
            return content

        frame_pattern = (
            r"(// GENERATOR-CONTRACT: DO NOT EDIT — patched from manifest\.frame_size by the generator\n"
            r"const FRAME_SIZE: u32 = )\d+(;)"
        )
        new_content, count = re.subn(frame_pattern, rf"\g<1>{int(frame_size)}\g<2>", content)

        if count != 1:
            raise RuntimeError(
                f"Failed to patch FRAME_SIZE in main.rs: expected exactly 1 match, got {count}.\n"
                "The template must contain the locked declaration (GENERATOR_RUNTIME_CONTRACT.md §2.1):\n"
                "  // GENERATOR-CONTRACT: DO NOT EDIT — patched from manifest.frame_size by the generator\n"
                "  const FRAME_SIZE: u32 = 256;\n"
                "If the template changed, update the contract doc FIRST, then this regex."
            )

        logger.info("Patched FRAME_SIZE → %d.", int(frame_size))
        return new_content

    def _build_sprite_entries(self, manifest: dict) -> list[str]:
        """从 manifest 构建 SPRITE_SHEETS Rust 5 元组条目列表。

        契约 GENERATOR_RUNTIME_CONTRACT.md §1：``(AnimState, &[u8], f32, bool, f32)``
        即 ``(状态, PNG字节, fps, 是否循环, duration_secs)``。

        manifest 格式（由 SpritePacker 生成）：
        {
            "body_type": "humanoid",
            "actions": {
                "idle": {
                    "file": "idle_sheet.png",
                    "fps": 12,
                    "loop": true,
                    "frame_count": 12,
                    "duration_secs": 3.0,
                    "rust_variant": "Idle"  // 可选
                },
                ...
            }
        }

        生成前 fail-fast：每个 action 解析出的 rust_variant 必须 ∈ KNOWN_ANIM_STATES，
        否则抛 ValueError（含非法 variant + action 名 + body_type），在编译前阻断。
        """
        actions_meta: dict = manifest.get("actions", {})
        body_type = manifest.get("body_type", "unknown")
        entries: list[str] = []

        for action_name, meta in actions_meta.items():
            file_name = meta.get("file", f"{action_name}_sheet.png")
            fps = float(meta.get("fps", 12))
            loop = "true" if meta.get("loop", True) else "false"
            rust_variant = resolve_rust_variant(action_name, meta.get("rust_variant"))

            # fail-fast 白名单校验（编译前阻断未注册变体）
            validate_rust_variant(rust_variant, action_name, body_type)

            # duration_secs：优先 manifest 显式值；缺失则用 frame_count/fps 兜底。
            duration_secs = meta.get("duration_secs")
            if duration_secs is None:
                frame_count = int(meta.get("frame_count", 0))
                duration_secs = (frame_count / fps) if fps > 0 else 0.0
            duration_text = _fmt_f32(round(float(duration_secs), 2))

            entry = (
                f"    (AnimState::{rust_variant}, "
                f'include_bytes!("../assets/{file_name}"), '
                f"{_fmt_f32(fps)}, {loop}, {duration_text}),"
            )
            entries.append(entry)

        return entries
