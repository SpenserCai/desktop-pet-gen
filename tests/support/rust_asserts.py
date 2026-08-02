"""生成产物（`main.rs`）的断言助手。

生成产物的正确性由这些断言集中守护，`test_golden_sample.py` 与
`test_pipeline_replay.py` 共用，避免各写一套正则。

契约细节见 `docs/standards/GENERATOR_RUNTIME_CONTRACT.md`。
"""

from __future__ import annotations

import re
from pathlib import Path

# 历史缺陷标记：早期实现用 Bevy TextureAtlas 切帧，导致渲染成灰方块；
# 现行实现是 CPU 逐帧切片。这两个符号一旦重新出现在生成产物里，说明退化了。
LEGACY_ATLAS_MARKERS = ("TextureAtlas", "UVec2::splat")

# 只匹配锁定注释锚定的真实 const 块，排除 doc-comment 示例（`///` 开头）
_SPRITE_BLOCK_RE = re.compile(
    r"^// GENERATOR-CONTRACT: DO NOT EDIT[^\n]*\n"
    r"const SPRITE_SHEETS: &\[\(AnimState, &\[u8\], f32, bool, f32\)\] = &\[(.*?)\];",
    re.DOTALL | re.MULTILINE,
)

_ENTRY_RE = re.compile(
    r'\(AnimState::(?P<variant>\w+),\s*include_bytes!\("(?P<asset>[^"]+)"\),\s*'
    r"(?P<fps>\d+(?:\.\d+)?),\s*(?P<loop>true|false),\s*(?P<duration>\d+(?:\.\d+)?)\),"
)


def sprite_sheet_entries(main_rs: Path) -> list[re.Match[str]]:
    """解析真实 `SPRITE_SHEETS` const 块里的 5 元组条目。

    Returns:
        正则匹配对象列表，可用 `m["variant"] / m["asset"] / m["fps"] / m["loop"] / m["duration"]` 取值。
    """
    text = main_rs.read_text(encoding="utf-8")
    block = _SPRITE_BLOCK_RE.search(text)
    assert block, f"{main_rs} 未找到 GENERATOR-CONTRACT 锚定的 SPRITE_SHEETS const 块"
    return list(_ENTRY_RE.finditer(block.group(1)))


def assert_frame_size(main_rs: Path, expected: int) -> None:
    """断言 `const FRAME_SIZE: u32 = <expected>;`。"""
    text = main_rs.read_text(encoding="utf-8")
    match = re.search(r"const FRAME_SIZE: u32 = (\d+);", text)
    assert match, f"{main_rs} 未找到 const FRAME_SIZE 声明"
    assert int(match.group(1)) == expected, (
        f"{main_rs} FRAME_SIZE={match.group(1)}，期望 {expected}"
    )


def assert_no_legacy_atlas_markers(main_rs: Path) -> None:
    """断言生成产物不含历史 TextureAtlas 切帧代码残留。"""
    text = main_rs.read_text(encoding="utf-8")
    for marker in LEGACY_ATLAS_MARKERS:
        assert text.count(marker) == 0, f"{main_rs} 仍含历史切帧标记 '{marker}'"


def assert_project_structure(project_dir: Path) -> None:
    """断言生成项目的目录结构完整（模板整体复制这一隐式契约）。"""
    for rel in (
        "Cargo.toml",
        "Cargo.lock",
        "src/main.rs",
        "src/config.rs",
        "src/command.rs",
        "src/animation.rs",
        "src/interaction.rs",
        "src/window.rs",
        "src/ui/mod.rs",
        "src/ui/menu.rs",
        "src/ui/hud.rs",
        "src/ui/toast.rs",
        "src/ui/icons.rs",
        "src/ui/theme.rs",
        "assets/fallback.png",
    ):
        assert (project_dir / rel).exists(), f"生成项目缺少 {rel}"
    assert not (project_dir / "target").exists(), "模板的 target/ 不应被复制"
