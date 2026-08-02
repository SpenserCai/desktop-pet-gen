"""运行时生成模块 — 从 sprite 资产生成可编译的 Rust 桌面宠物项目。

导出:
    RuntimeGenerator: Rust 项目生成器（模板复制 + SPRITE_SHEETS/FRAME_SIZE patch）
    compile_project: cargo build 封装
    resolve_rust_variant: 动作名 → AnimState 变体解析
    validate_rust_variant: AnimState 变体白名单 fail-fast 校验
    KNOWN_ANIM_STATES: AnimState 白名单（契约 §3）
"""

from pet_generator.runtime_gen.compiler import compile_project
from pet_generator.runtime_gen.rust_project import (
    ANIM_STATE_MAP,
    KNOWN_ANIM_STATES,
    RuntimeGenerator,
    resolve_rust_variant,
    snake_to_pascal,
    validate_rust_variant,
)

__all__ = [
    "ANIM_STATE_MAP",
    "KNOWN_ANIM_STATES",
    "RuntimeGenerator",
    "compile_project",
    "resolve_rust_variant",
    "snake_to_pascal",
    "validate_rust_variant",
]
