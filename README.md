# 🐾 desktop-pet-gen

[![CI](https://github.com/SpenserCai/desktop-pet-gen/actions/workflows/ci.yml/badge.svg)](https://github.com/SpenserCai/desktop-pet-gen/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Bevy 0.18](https://img.shields.io/badge/bevy-0.18-orange.svg)](https://bevyengine.org/)

**把一张图片变成会动的跨平台桌面宠物。** Python 管线调用 AI 生成帧动画并打包成
sprite sheet，再生成一个 Rust/Bevy 的透明置顶桌宠项目 —— 资产编译期内嵌，
运行期零网络零文件写入，产物是可独立分发的可执行文件。

- 📖 [文档](docs/README.md) · 🤝 [贡献指南](CONTRIBUTING.md) · 📋 [变更日志](CHANGELOG.md) · 🔒 [安全策略](SECURITY.md)

## ✨ 核心特性

- **端到端 AI 管线**：从一张图片到可运行桌面宠物，8 个阶段全自动编排
- **智能体型分类**：AI 视觉模型自动识别宠物体型（人形 / 四足 / 无肢 / 物体），匹配专属动作集
- **多 Provider 支持**：图像生成（Azure GPT-Image-2 / 百炼 WAN）、视频生成（Kling / WAN 2.7）可自由切换
- **分类感知生成**：标准化、姿态、视频 prompt 均按体型定制，保证动画质量
- **原生 Rust 运行时**：生成透明窗口桌面宠物，数据驱动动画、可用性感知状态机、HUD 状态面板、成就系统、交互打磨；系统托盘为可选 feature（见下文 [Rust 运行时特性](#rust-运行时特性)）
- **配置聚合中心**：CLI > 环境变量 > 默认值三级优先级，`to_dict()`/`from_dict()` 预留 UI 扩展

## 🚀 快速开始

### 安装

```bash
# 需要 Python >= 3.12、Rust 稳定版工具链 (cargo)、ffmpeg
git clone https://github.com/SpenserCai/desktop-pet-gen.git
cd desktop-pet-gen

python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # 或 uv venv && uv pip install -e ".[dev]"

# 拉取去背景模型（约 658 MB，不入版本库；带 SHA256 校验与断点续传）
python scripts/fetch_models.py            # 全部
python scripts/fetch_models.py --model u2net   # 只要默认模型（168 MiB）
python scripts/fetch_models.py --check    # 只校验本地文件
```

模型来源为 ModelScope（`AI-ModelScope/u2net`、`AI-ModelScope/RMBG-2.0`），
可用 `MODELSCOPE_ENDPOINT` 指向镜像。清单与校验值见 `scripts/fetch_models.py --list`。

### 最简用法

```bash
# 设置 API Keys
export AZURE_OPENAI_API_KEY="sk-..."
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com"
export DASHSCOPE_API_KEY="sk-..."

# 一键生成（推荐用 -u 强制无缓冲输出，配合 | tee 时日志实时可见）
python -u -m pet_generator -i photo.jpg -n my-cat
```

> 💡 管线支持断点续跑：中断后重跑会自动跳过已生成的姿态图/视频/帧（日志显示"缓存命中"），不重复调用 AI API。

## 📖 CLI 用法示例

```bash
# 基础用法：AI 自动分类 + 全动作生成
pet-gen -i cat.png -n my-cat

# 手动指定体型 + 动作子集（跳过 AI 分类）
pet-gen -i pixel.png --body-type quadruped --actions idle,walk,sit

# 调试模式：跳过视频生成 + 不编译（快速验证管线）
pet-gen -i art.png --skip-video --no-compile

# 切换 Provider
pet-gen -i robot.png --image-provider bailian --video-provider wan27

# 高质量去背景（默认 u2net 快速；rmbg 质量更高但更慢）
pet-gen -i cat.png --bg-model rmbg
```

## 🔄 管线阶段概览

| Stage | 名称 | 职责 | 输出 |
|:-----:|------|------|------|
| 0 | Classifier | AI 视觉分类体型 | `body_type` + 置信度 |
| 1 | Standardizer | 分类感知图像标准化 | 统一风格 PNG |
| 2 | PoseGenerator | 生成各动作尾帧/关键姿态 | 每动作 1 张 PNG |
| 3 | VideoGenerator | 首帧→尾帧过渡视频 | 每动作 1 个 MP4 |
| 4 | FrameExtractor | 视频抽帧（ffmpeg） | 每动作 N 帧 PNG |
| 5 | BackgroundRemover | U2-Net / RMBG-2.0 ONNX 去背景（跨平台自动加速） | 透明背景帧 |
| 6 | SpritePacker | Sprite Sheet 打包 | atlas PNG + manifest.json |
| 7 | RuntimeGenerator | Rust 项目生成 + cargo build | 可执行文件 |

## 🔑 环境变量

| 变量 | 用途 | 必需 |
|------|------|:----:|
| `AZURE_OPENAI_API_KEY` | Azure GPT-Image-2 图像生成 | 默认 provider 时必需 |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI 端点 | 默认 provider 时必需 |
| `DASHSCOPE_API_KEY` | 百炼 API（分类器 + 百炼 provider） | ✅ |
| `U2NET_MODEL_PATH` | 自定义 U2-Net 模型路径 | 可选 |
| `RMBG_MODEL_PATH` | 自定义 RMBG-2.0 模型路径 | 可选 |
| `PET_BG_MODEL` | 去背景模型（`u2net` \| `rmbg`，默认 `u2net`） | 可选 |

> 完整环境变量列表见 [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

## 🎭 去背景模型

Stage 5 支持两种 ONNX 去背景模型，通过 `--bg-model` 或 `PET_BG_MODEL` 切换：

| 模型 | 特点 | 适用 |
|------|------|------|
| `u2net`（默认） | 体积小（~176MB）、速度快 | 快速测试、批量生成 |
| `rmbg` | RMBG-2.0 (BiRefNet fp16, ~513MB)，边缘质量更高 | 追求抠图质量 |

- 两个模型放在 `models/`（`u2net.onnx` / `rmbg-2.0.onnx`），**不入版本库**（单文件超 Git 上限），
  首次使用请运行 `python scripts/fetch_models.py` 从 ModelScope 拉取（带 SHA256 校验与断点续传）。
- **跨平台自动加速**：运行时按 `CUDAExecutionProvider`(Linux/Windows NVIDIA) → `CoreMLExecutionProvider`(macOS) → `CPUExecutionProvider` 的优先级自动探测并启用最优 EP， unsupported 算子自动回落 CPU，保证正确性。实际启用的 EP 会打印在日志中。
- 注：macOS 上 CoreML 对 RMBG-2.0 的算子覆盖率较低，`rmbg` 推理明显慢于 `u2net`；在 NVIDIA CUDA 环境二者加速效果均更好。

## 🐾 Rust 运行时特性

Stage 7 从 `pet-runtime/` 模板生成独立可编译的 Rust 桌面宠物项目。运行时特性与实现一一对应（详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 的「运行时架构」与 [docs/standards/GENERATOR_RUNTIME_CONTRACT.md](docs/standards/GENERATOR_RUNTIME_CONTRACT.md)）：

- **可用性感知状态机**：`base / action / dragging` 三层，渲染优先级 `drag > action > base`。mood→base 映射与「实际加载成功的动画集 `available`」取交集——非人形体型缺失某动画时 base 回落 Idle（body-type-agnostic）。自主行为的触发条件是「无 action 且未拖动」，**不要求 base==Idle**，因此 Sleepy/Hungry 心情下依旧活跃。
- **action 定时回落 + 看门狗**：循环动画必带持续时间，倒计时结束回落 base；非循环动画播完即止；另有 20s 看门狗兜底，损坏 sheet 也不会卡死。菜单 Sleep 为定时动作（约 10s 自动唤醒）。
- **窗口拖动（物理像素锚点）**：以 `WindowAnchor` 为唯一位置事实源（启动落在主显示器右下角，OS `WindowMoved` 持续校正），拖动增量取「窗口内物理光标位置 − 抓取点」，自校正、不漂移、跨平台一致；拖动带 squash-and-stretch 弹性反馈。
- **精确点击**：左键必须落在宠物**不透明像素**上才生效（alpha 命中测试）；位移 < 4px 算抚摸，越过阈值算拖动；菜单/HUD 区域优先吞掉指针，菜单外点击关闭菜单。
- **数据驱动右键菜单**：在光标处弹出并夹取进窗口；行 = Feed / Play + **每个可用动画各一行** + Sleep（有 sheet 时）+ Quit。图标由 UI 节点几何绘制（**零字体依赖**，因为 Bevy 内嵌默认字体只覆盖 ASCII，emoji 会渲染成方块）。
- **HUD + Toast**：左下实时显示 `NRG / HAP / HGR` 与**当前生效状态名**（便于验证状态机）；动作反馈与成就解锁通过顶部 Toast 上屏，不再只打印到 stdout。
- **成就系统（4 项）**：First Feed / Pet Lover（抚摸 10 次）/ Dancer（3 次主动动作，body-type-agnostic）/ Survivor（健康存活 5 分钟）。
- **意图消息总线**：所有输入面（精灵点击、菜单、托盘、未来快捷键）只发 `PetCommand`，由唯一执行器落实效果——新增输入面无需了解生命值与状态机。
- **数据驱动 5 元组契约**：动画由生成器注入的 `SPRITE_SHEETS: &[(AnimState, &[u8], f32, bool, f32)]` + `FRAME_SIZE` 常量驱动，资产 `include_bytes!` 编译期内嵌，运行期零文件写入。

### 构建运行时（含可选系统托盘）

生成的项目默认即可构建运行，**系统托盘为可选 feature，默认关闭**（关闭时 `tray.rs` 编译为 no-op stub，不引入 `tray-icon`/`muda` 依赖，保证无依赖环境也能编译）：

```bash
cd build/<your-pet>     # 或管线输出目录 output/<your-pet>

# 默认构建（无系统托盘）
cargo build --release
./target/release/<your-pet>

# 启用系统托盘（macOS 验证可用：Show / Hide / Quit 菜单）
cargo build --release --features tray
./target/release/<your-pet>
```

> 说明：托盘功能在 macOS 已验证；Windows/Linux 在 feature 关闭时可编译，feature 开启时的跨平台行为需各自验证（CI 会验证 feature 开启时可编译）。

## 🧪 测试与门禁

测试系统完全独立：**零网络、零 API Key、零 ONNX 权重、零临时目录依赖**，
一条命令即可在任意干净克隆上跑通。

```bash
ruff check . && ruff format --check . && pytest -q      # Python：静态检查 + 格式 + 测试
cd pet-runtime && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test   # Rust：格式 + clippy + 测试
cd .. && scripts/smoke_run.sh                          # 运行期冒烟：自造项目 → 构建 → 运行 → 日志断言
```

测试素材有两个来源，分工明确：

| 来源 | 位置 | 用途 |
|------|------|------|
| **真实 AI 产物**（录制） | `tests/fixtures/ai_pipeline/` | 「素材过管线」回归。1024² RGB 无 alpha、主体不居中、真实边缘噪声——合成造不出的形态。同时作为回放数据，让**需要调接口的阶段**（分类/标准化/尾帧）进入自动化测试 |
| **程序化合成** | `tests/support/synth.py` | 边界形态：非正方、奇数尺寸、alpha 渐变、单帧动作、帧数不等、损坏帧 |

`tests/support/fakes.py` 提供回放型假 provider（Vision / ImageGen / VideoGen）与直通抠图器，
因此 `tests/test_pipeline_replay.py` 能在无网络无模型的环境里跑完 Stage 0→7。
临时产物一律落 `build/`（已 gitignore），仓库零残留。详见
[docs/standards/CODE_QUALITY_GATES.md](docs/standards/CODE_QUALITY_GATES.md)。

## 📁 项目结构

```
desktop-pet-gen/
├── pyproject.toml              # 项目元数据与依赖
├── models/                     # 去背景 ONNX 模型（gitignore，由 scripts/fetch_models.py 拉取）
├── pet_generator/              # Python 管线主包
│   ├── cli.py                  # 统一 CLI 入口
│   ├── pipeline.py             # 管线编排器 (Stage 0~7)
│   ├── config/                 # 聚合配置中心
│   │   ├── settings.py         # Settings 单一事实源
│   │   ├── classifier_config.py
│   │   └── actions/            # 4 套体型动作集
│   ├── providers/              # AI 服务抽象层
│   │   ├── base.py             # 抽象接口 + GenerationResult
│   │   ├── image_gen/          # Azure / 百炼图像
│   │   ├── video_gen/          # Kling / WAN 视频
│   │   └── vision/             # 视觉理解 (Qwen-VL)
│   ├── prompts/                # Prompt 模板库
│   ├── stages/                 # 7 个管线阶段实现
│   └── runtime_gen/            # Rust 项目生成 + 编译
├── pet-runtime/                # Rust 桌面宠物运行时模板
│   ├── Cargo.toml
│   ├── assets/fallback.png
│   └── src/
│       ├── main.rs             # 嵌入资产解码 + 插件装配 + 帧内流水线
│       ├── config.rs           # 唯一调参面（几何/阈值/时长/数值）
│       ├── command.rs          # PetCommand 意图总线 + 唯一执行器
│       ├── window.rs           # 透明置顶窗口 + 物理像素位置锚点
│       ├── animation.rs        # AnimState / 状态机 / 帧播放
│       ├── interaction.rs      # 拖动 / alpha 命中测试 / squash
│       ├── pet.rs behavior.rs achievements.rs tray.rs
│       └── ui/                 # theme / icons / menu / hud / toast
├── scripts/                    # fetch_models.py（模型分发）+ smoke_run.sh（GUI 冒烟取证）
├── tests/                      # 独立测试系统（100 个用例，零网络零模型）
│   ├── conftest.py             # 共享夹具（只读夹具路径、模板路径）
│   ├── support/                # 测试支撑层：synth（合成工厂）/ fakes（录制回放）/ rust_asserts
│   └── fixtures/               # 只读夹具：portraits/ 输入原图 + ai_pipeline/ 真实 AI 录制
├── build/                      # 临时产物唯一落点（gitignore，可随时整目录删）
└── docs/                       # 文档
    ├── README.md               # 文档索引与维护约定
    ├── ARCHITECTURE.md         # 架构设计（mermaid：项目构成/管线/运行时分层/状态机/拖动时序）
    ├── CONFIGURATION.md        # 配置参考（Python Settings + 运行时 config.rs）
    └── standards/              # 规范：检查标准、跨语言契约、扩展方式、运行时 UX
```

## 📚 详细文档

- [文档索引](docs/README.md) — 参考层与规范层的分工与维护约定
- [架构设计](docs/ARCHITECTURE.md) — 项目构成、管线流程、Provider 体系、运行时分层与交互时序
- [配置参考](docs/CONFIGURATION.md) — Settings 字段、环境变量、CLI 参数、运行时调参面
- [规范目录](docs/standards/README.md) — 检查标准、生成器↔运行时契约、扩展动作/机制/提示词、运行时 UX

## 🤝 参与贡献

欢迎 issue 与 PR。开发环境搭建、提交前检查、代码与测试约定见
**[CONTRIBUTING.md](CONTRIBUTING.md)**；社区准则见
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

只跑测试**不需要** AI 服务凭据，也不需要下载模型 —— 测试通过录制回放覆盖这些路径。

## 🔒 安全

漏洞请按 [SECURITY.md](SECURITY.md) 私下报告，不要开公开 issue。
凭据一律从环境变量读取，仓库内不含任何密钥。

## 📄 License

[MIT](LICENSE) © SpenserCai

第三方模型（U^2-Net、RMBG-2.0）由 `scripts/fetch_models.py` 按需下载，不随本仓库分发。
其许可条款、AI 生成素材的权利归属见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
—— 特别注意 **RMBG-2.0 对商业使用有限制**。
