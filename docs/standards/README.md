# 规范目录

规范回答「怎么改才对」，是代码评审的依据。每条规范尽量绑定一个自动化守护。

| 文档 | 覆盖范围 | 主要守护 |
|------|---------|---------|
| [CODE_QUALITY_GATES.md](CODE_QUALITY_GATES.md) | 提交前必须通过的检查（cargo fmt/clippy/test/build/tray + ruff check/format + pytest + 运行期冒烟）、测试分层与铁律 | 门禁命令本身 + `.github/workflows/ci.yml` |
| [GENERATOR_RUNTIME_CONTRACT.md](GENERATOR_RUNTIME_CONTRACT.md) | Python ↔ Rust 唯一强耦合：`SPRITE_SHEETS`、`FRAME_SIZE`、`AnimState` 白名单、manifest | `tests/test_runtime_gen_contract.py` |
| [EXTEND_ACTIONS.md](EXTEND_ACTIONS.md) | 新增一个动画的五步清单 | `test_all_body_type_variants_known`、`action_order_contains_no_bases_and_no_duplicates` |
| [EXTEND_MECHANISMS.md](EXTEND_MECHANISMS.md) | 新增体型 / Provider / 管线阶段 / 运行时系统与输入面 | 各层单测 + 门禁 |
| [EXTEND_PROMPTS.md](EXTEND_PROMPTS.md) | 提示词分层与调优流程 | 人工评审（附检查表） |
| [RUNTIME_UX.md](RUNTIME_UX.md) | 窗口坐标系、指针语义、菜单、字体 ASCII-only、渲染 | `test_template_ui_text_is_ascii_only`、`interaction.rs` 无头集成测试、菜单夹取/尺寸单测 |

## 优先级

冲突时按此顺序取舍：

1. **契约** —— 破坏 `GENERATOR_RUNTIME_CONTRACT.md` 会让生成链断裂，代价最高。
2. **门禁** —— 不允许为了赶进度放宽 `-D warnings` 或跳过测试。
3. **交互/UI 硬约束** —— ASCII-only 与坐标系规则来自真实缺陷，违反即回归。
4. **扩展规范** —— 风格与一致性问题，可在评审中讨论。
