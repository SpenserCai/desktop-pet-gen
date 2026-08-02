# 代码质量门禁

> 提交前必须全绿。任何一项失败都视为「未完成」，不得以「后续再修」放行。

## 一、门禁总表

| 检查项 | 命令 | 判定 |
|--------|------|------|
| Rust 格式 | `cargo fmt --check` | 无 diff 输出 |
| Rust 静态检查 | `cargo clippy --all-targets -- -D warnings` | 零告警（告警即错误） |
| Rust 测试 | `cargo test` | 全部通过 |
| Rust 发布构建 | `cargo build --release` | 成功且无告警 |
| 可选特性构建 | `cargo check --features tray` | 成功（feature-gated 代码不腐烂） |
| Python 静态检查 | `ruff check .` | 零告警 |
| Python 格式 | `ruff format --check .` | 无待格式化文件 |
| Python 测试 | `pytest -q` | 全部通过 |
| 运行期冒烟 | `scripts/smoke_run.sh` | 无 panic；日志出现动画加载、菜单尺寸、窗口定位、自主行为 |

Rust 检查在 `pet-runtime/`（模板）执行，生成产物同样适用；Python 检查在项目根执行。
运行期冒烟需要 `cargo` 与图形会话，只能本地跑。

## 二、一次跑完

前置：激活项目 Python 环境（`python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"`，
或用 `uv venv && uv pip install -e ".[dev]"`）。`pytest` 的 `pythonpath = ["."]` 已在
`pyproject.toml` 配好，测试不需要任何 `sys.path` 操作。

```bash
# Python（项目根）
ruff check . && ruff format --check . && pytest -q

# Rust 模板
cd pet-runtime
cargo fmt --check && \
cargo clippy --all-targets -- -D warnings && \
cargo test && \
cargo check --features tray && \
cargo build --release

# 运行期冒烟（需要 GUI 会话）
cd .. && scripts/smoke_run.sh
```

CI 工作流 `.github/workflows/ci.yml` 覆盖除运行期冒烟以外的全部检查。

## 三、运行期冒烟的判定

`scripts/smoke_run.sh` 自己用 `tests/fixtures/ai_pipeline/sprites_256` 的录制素材
在 `build/` 里生成项目并构建运行，不依赖任何预置产物。日志里必须能看到：

- 每个 sheet 一行 `Loaded animation <State>: N frames @ fps (loop=…, duration=…)`（≥5 条）；
- `Menu: N rows, estimated size Vec2(w, h)` 且 `h < WINDOW_SIZE`（否则菜单会被裁切）；
- `Window placed at IVec2(x, y) (physical), scale_factor …`；
- 运行窗口 >12 s 时出现 `Behavior: playing …`（自主行为链路通）；
- 全程无 `panic`。

## 四、测试分层与「守护什么」

| 层 | 位置 | 守护对象 |
|----|------|---------|
| Rust 纯函数单测 | 各模块 `#[cfg(test)]` | 状态机时序、命令语义、菜单派生、几何/夹取、颜色阈值、图标形状边界、通知格式 |
| Rust 无头集成测 | `interaction.rs` 测试段 | **拖动真的移动窗口**、点击宠物才抚摸、透明像素不响应、阈值内位移仍算点击、右键开关菜单、菜单外点击关闭 |
| 生成契约测 | `tests/test_runtime_gen_contract.py` | patch 正则 `count==1`、`FRAME_SIZE` 同步、白名单 fail-fast、`frame_count` 自检、真实模板端到端生成、UI ASCII-only |
| 素材过管线 | `tests/test_golden_sample.py` | 真实 AI 素材（1024² RGB 无 alpha）→ 打包 → 生成项目；256 录制路径与 512 重打包路径；无历史 `TextureAtlas` 残留；fallback 取自真实标准图 |
| 端到端回放 | `tests/test_pipeline_replay.py` | Stage 0→7 编排、`skip_video` 两帧路径、视频路径、断点续跑缓存、空帧动作隔离、`body_type_override` 短路 |
| 阶段单测 | `tests/test_sprite_packer.py`、`test_frame_extractor.py`、`test_bg_remover.py`、`test_classifier.py`、`test_pose_generator_parallel.py` | 打包边界、ffmpeg 容错、模型查找链与 EP 选择、分类容错与降级、Stage 2 并发语义 |
| 接口层单测 | `tests/test_providers.py`、`test_cli.py`、`test_fetch_models.py` | 重试/超时/错误归一化、工厂装配、CLI→Settings 映射、模型清单与校验 |

### 铁律

1. **测试不得依赖临时目录或人工前置步骤**。输入只能来自 `tests/fixtures/`（只读夹具）
   或 `tests/support/synth.py`（程序化合成）；产物只能写 `tmp_path`。
2. **需要调外部接口的阶段，用 `tests/support/fakes.py` 回放录制素材**，不得触网、
   不得依赖 API Key、不得加载 ONNX 权重。
3. **新增夹具前先问「能不能合成」**。只有「真实 AI 产物特性」才值得入版本库
   （见 `tests/fixtures/README.md`）。
4. **新增代码必须带守护**：改交互/状态机/菜单派生 → 补对应 Rust 层测试；
   改跨语言常量 → 补契约测试；修缺陷 → 补一个会因该缺陷失败的测试。

## 五、硬规则

1. **`-D warnings` 不可放宽**：不允许用 `#[allow(...)]` 掩盖 clippy 告警，除非在注释里写明原因
   （现存唯一豁免：`AnimState` 变体 `dead_code` —— 变体由生成器注入的 `SPRITE_SHEETS` 构造）。
2. **不得编辑 `// GENERATOR-CONTRACT:` 锁定块**：见
   [GENERATOR_RUNTIME_CONTRACT.md](GENERATOR_RUNTIME_CONTRACT.md)。必须变更时先改契约文档。
3. **UI 文案只能是 ASCII**：见 [RUNTIME_UX.md](RUNTIME_UX.md)，由
   `test_template_ui_text_is_ascii_only` 守护。
4. **运行时零文件写入**：不得引入 config/appdata/temp 写入；资产用 `include_bytes!` 内嵌。
5. **常量集中**：新的可调数值放 `pet-runtime/src/config.rs`，不要散落在系统里。
6. **ruff 豁免必须写明理由**：`pyproject.toml` 的 `per-file-ignores` 每条都要有注释
   （现存两条：LLM 提示词 Schema 字面文本、契约锁定注释必须逐字节一致）。
7. **Shell 脚本里变量紧跟非 ASCII 字符必须写 `${var}`**：macOS 自带 bash 3.2 解析 `$var`
   时会把紧随的多字节字节并入变量名，在 `set -u` 下变成 unbound variable 并**静默退出**
   （曾导致 `smoke_run.sh` 整段日志断言被跳过而脚本仍"看起来正常"）。新增脚本后用
   `grep -nP '\$[A-Za-z_]\w*(?=[^\x00-\x7f])'` 自查。
8. **不提交**：`.DS_Store`、`target/`、`build/`、`models/*.onnx`（体积超 Git 上限，
   用 `scripts/fetch_models.py` 拉取）。
