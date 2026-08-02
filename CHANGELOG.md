# Changelog

本项目的所有重要变更都记录在此文件。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added

- **模型分发**：`scripts/fetch_models.py` 从 ModelScope 拉取去背景 ONNX 权重，
  带 SHA256 校验、HTTP Range 断点续传、`--check`/`--list`/`--force`，
  支持 `MODELSCOPE_ENDPOINT` 指向镜像。权重不再随仓库分发。
- **独立测试系统**：`tests/` 不依赖网络、API Key、ONNX 权重或任何临时目录。
  - `tests/fixtures/` 只读夹具：输入原图 + 一次真实管线运行的录制产物（分类响应、
    标准图、10 个动作尾帧、10 张 sprite sheet）。
  - `tests/support/synth.py` 程序化合成边界素材（非正方、奇数尺寸、alpha 渐变、
    单帧动作、损坏帧）。
  - `tests/support/fakes.py` 回放型 provider，让需要调用 AI 接口的阶段
    （分类 / 标准化 / 尾帧 / 视频）进入自动化回归。
  - 新增覆盖：真实素材过管线、端到端管线回放（含断点续跑与空帧隔离）、
    打包边界、ffmpeg 容错、模型查找与 ONNX Execution Provider 选择、
    分类容错与降级、Provider 重试/超时、CLI 参数映射。
- **CI**：GitHub Actions 工作流覆盖 Python（ruff check/format、pytest）与
  Rust（fmt、clippy、test、可选 tray 特性、release 构建）。
- **冒烟脚本**：`scripts/smoke_run.sh` 自行用录制素材生成项目、构建、运行并断言
  运行期日志（动画加载、菜单尺寸、窗口定位、自主行为、无 panic），产物落 `build/`。
- 开源工程文件：LICENSE、CONTRIBUTING、CODE_OF_CONDUCT、SECURITY、
  issue/PR 模板、dependabot、pre-commit、EditorConfig。

### Changed

- **运行时重构为分层插件结构**：新增集中调参面 `config.rs`、意图消息总线
  `command.rs`（所有输入面只发命令，由唯一执行器落实效果）、UI 拆分为
  `ui/{theme,icons,menu,hud,toast}`；帧内系统流水线在 `main.rs` 显式固化。
- **窗口尺寸 256×256 → 300×300**，纹理过滤由 nearest 改为线性。
- Python 侧补齐静态检查门禁（ruff），全量代码格式化。
- 测试与文档中的内部编号（门禁 `G<n>`、缺陷 `D<n>`）改为直白描述。

### Fixed

- **窗口拖动完全失效**：旧实现依赖 `WindowPosition::At` 分支，而窗口位置默认是
  `Automatic`，分支永不命中；且 `MouseMotion` 的增量在 macOS 是逻辑点、
  在 Windows 是原始设备增量，与物理像素的窗口位置混用会漂移。
  现以 `WindowAnchor`（物理像素）为唯一位置事实源，位移取
  「窗口内物理光标位置 − 抓取点」，自校正且跨平台一致。
- **右键菜单被窗口裁切**：菜单估算高度超过窗口高度，最后一行落在窗口外，
  既看不见也点不到。现在菜单在光标处弹出并夹取进窗口，且有单元测试断言
  「满行菜单高度 < 窗口高度」。
- **点击语义混乱**：Feed 与 Play 曾映射到同一个动画；左键释放不做命中判定，
  点击窗口任意位置都会触发抚摸。现在菜单为每个可用动画各生成一行，
  抚摸必须命中宠物的不透明像素（alpha 命中测试）。
- **图标渲染成方块**：Bevy 内嵌默认字体的 cmap 只覆盖 95 个码位（最大 `U+007E`），
  emoji 必然是 tofu。改为用 UI 节点几何绘制图标，UI 文案约束为 ASCII-only 并加测试守护。
- **状态机死区**：拖动时无条件冻结帧（缺 drag 动画时看起来卡死）；自主行为要求
  base 为 Idle，导致 Sleepy/Hungry 心情后永久静止；非循环动作无超时兜底。
  现在冻结有条件、自主行为只要求「无动作且未拖动」、动作有看门狗。
- **成就与动作反馈不可见**：原先只打印到 stdout，GUI 启动时看不到。改为 Toast 上屏。
- **降级图查找路径错位**：`_copy_fallback` 多退一级目录，导致 `assets/fallback.png`
  永远是模板占位图而不是本次生成的标准图。

## [0.1.0] - 2026-08-01

### Added

- 首个可用版本：Stage 0–7 端到端管线（分类 → 标准化 → 尾帧 → 视频 → 抽帧 →
  去背景 → sprite 打包 → Rust 项目生成与编译）。
- 4 套体型动作集（humanoid / quadruped / limbless / object）与分类感知提示词。
- Provider 抽象层：图像（Azure GPT-Image / 百炼）、视频（Kling / WAN）、视觉理解。
- Rust + Bevy 透明置顶运行时：数据驱动 sprite 动画、状态机、HUD、成就、
  可选系统托盘；资产编译期内嵌，运行期零文件写入。
- 生成器 ↔ 运行时契约（`SPRITE_SHEETS` 5 元组、`FRAME_SIZE`、`AnimState` 白名单）
  与对应回归测试。
