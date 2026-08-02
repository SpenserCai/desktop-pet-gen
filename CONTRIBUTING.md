# 贡献指南

感谢你考虑为这个项目贡献代码。这份文档说明如何搭环境、跑检查、提交改动。

## 环境准备

需要 **Python ≥ 3.12**、**Rust 稳定版工具链**、**ffmpeg**。

```bash
git clone https://github.com/SpenserCai/desktop-pet-gen.git
cd desktop-pet-gen

# Python 环境（任选其一）
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
uv venv && uv pip install -e ".[dev]"

# 去背景模型（约 658 MB，不随仓库分发）
python scripts/fetch_models.py

# 可选：启用提交前自动检查
pre-commit install
```

跑管线需要 AI 服务凭据（见 [docs/CONFIGURATION.md](docs/CONFIGURATION.md)）。
**只跑测试不需要任何凭据或模型** —— 测试通过录制回放覆盖这些路径。

## 提交前必须通过的检查

```bash
# Python
ruff check .
ruff format --check .
pytest -q

# Rust 运行时模板
cd pet-runtime
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
cargo check --features tray
cargo build --release
```

需要图形会话的运行期冒烟（可选，但改动运行时交互时强烈建议跑）：

```bash
scripts/smoke_run.sh
```

判定标准与豁免规则见 [docs/standards/CODE_QUALITY_GATES.md](docs/standards/CODE_QUALITY_GATES.md)。
CI 会自动执行除冒烟以外的全部检查。

## 代码约定

- **Python**：ruff 管格式与静态检查（行宽 100，规则集 `E,F,I,W,B,UP`）。
  新增豁免必须写在 `pyproject.toml` 的 `per-file-ignores` 并附理由注释。
- **Rust**：`cargo fmt` 管格式；clippy 以 `-D warnings` 运行，不允许用
  `#[allow(...)]` 掩盖告警（除非注释写明原因）。
- **不要编辑 `// GENERATOR-CONTRACT:` 锁定块** —— 那是 Python 生成器按正则注入的锚点，
  改动会让生成失败。需要变更先改
  [docs/standards/GENERATOR_RUNTIME_CONTRACT.md](docs/standards/GENERATOR_RUNTIME_CONTRACT.md)。
- **运行时 UI 文案只能是 ASCII**：Bevy 内嵌默认字体只覆盖 `U+0020..U+007E`，
  非 ASCII 会渲染成方块。图标用 UI 节点几何绘制。详见
  [docs/standards/RUNTIME_UX.md](docs/standards/RUNTIME_UX.md)。
- **运行时零文件写入**：不引入 config/appdata/temp 写入，资产用 `include_bytes!` 内嵌。
- **新的可调数值放 `pet-runtime/src/config.rs`**，不要散落在各系统里。
- **Shell 脚本中变量紧跟非 ASCII 字符必须写 `${var}`**（macOS 自带 bash 3.2 会把多字节
  字节并入变量名，`set -u` 下静默退出）。

## 测试约定

| 要求 | 说明 |
|------|------|
| 不依赖外部世界 | 测试不得触网、不得读 API Key、不得加载 ONNX 权重 |
| 输入只有两个来源 | `tests/fixtures/`（只读夹具）或 `tests/support/synth.py`（程序化合成） |
| 产物只写 `tmp_path` | 仓库内不留任何残留；临时构建产物落 `build/` |
| 新增夹具先问「能不能合成」 | 只有「真实 AI 产物特性」才值得入库，见 `tests/fixtures/README.md` |
| 修缺陷必须补测试 | 补一个「没有这次修复就会失败」的测试 |

需要调用 AI 接口的阶段，用 `tests/support/fakes.py` 的回放型 provider。

## 提交与 PR

- 分支名建议 `feat/...`、`fix/...`、`docs/...`、`refactor/...`。
- 提交信息用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)，
  例：`fix(runtime): 修正拖动时的物理像素换算`。
- 一个 PR 只做一件事；把无关的格式化改动拆出去。
- PR 描述请写：改了什么、为什么、怎么验证的（贴门禁输出）。
- 用户可见的变更请在 [CHANGELOG.md](CHANGELOG.md) 的 `Unreleased` 段落加一条。

## 扩展方向的专门文档

| 想做的事 | 读这个 |
|---------|--------|
| 新增动作 | [docs/standards/EXTEND_ACTIONS.md](docs/standards/EXTEND_ACTIONS.md) |
| 新增体型 / Provider / 管线阶段 / 运行时系统 | [docs/standards/EXTEND_MECHANISMS.md](docs/standards/EXTEND_MECHANISMS.md) |
| 调整提示词 | [docs/standards/EXTEND_PROMPTS.md](docs/standards/EXTEND_PROMPTS.md) |
| 了解整体结构 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |

## 报告问题

Bug 与功能请求走 GitHub Issues（有模板）。安全问题请按
[SECURITY.md](SECURITY.md) 私下报告，不要开公开 issue。
