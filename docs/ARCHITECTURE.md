# 架构设计文档

> desktop-pet-gen — AI 驱动的桌面宠物生成器（Python 管线 + Rust/Bevy 运行时）

## 目录

- [项目构成](#项目构成)
- [核心管线流程](#核心管线流程)
- [生成器模块依赖](#生成器模块依赖)
- [数据流](#数据流)
- [Provider 体系](#provider-体系)
- [运行时架构](#运行时架构)
  - [模块分层](#模块分层)
  - [帧内系统流水线](#帧内系统流水线)
  - [动画状态机](#动画状态机)
  - [指针交互与窗口拖动](#指针交互与窗口拖动)
  - [Overlay UI](#overlay-ui)
- [生成器 ↔ 运行时契约](#生成器--运行时契约)
- [设计原则](#设计原则)
- [错误处理策略](#错误处理策略)
- [扩展点索引](#扩展点索引)

---

## 项目构成

```mermaid
flowchart TB
    subgraph REPO["desktop-pet-gen/"]
        direction TB

        subgraph GEN["pet_generator/ — Python 生成管线"]
            CLI["cli.py / __main__.py<br/>命令行入口"]
            PIPE["pipeline.py<br/>Stage 0-7 编排"]
            CFG["config/<br/>Settings + 动作集注册表"]
            STG["stages/<br/>7 个管线阶段"]
            PRV["providers/<br/>AI 服务抽象层"]
            PRM["prompts/<br/>提示词模板库"]
            RTG["runtime_gen/<br/>Rust 项目生成 + 编译"]
        end

        subgraph TPL["pet-runtime/ — Rust 运行时模板"]
            RSRC["src/ 10 模块 + ui/ 5 子模块"]
            RAST["assets/fallback.png"]
            RTOML["Cargo.toml (bevy 0.18)"]
        end

        subgraph DOC["docs/ — 文档体系"]
            DARC["ARCHITECTURE.md / CONFIGURATION.md"]
            DSTD["standards/ 规范与门禁"]
            DTSK["tasks/ 自包含任务文档"]
        end

        TST["tests/ — pytest 回归<br/>fixtures 只读夹具 + support 合成/回放"]
        SCR["scripts/ — 模型分发 + GUI 冒烟"]
    end

    IMG["输入图片"] --> CLI
    CLI --> PIPE
    PIPE --> STG --> PRV
    STG --> PRM
    PIPE --> RTG
    RTG -->|复制模板 + patch 常量| OUT["generated-pets/&lt;name&gt;/<br/>独立 Rust 项目"]
    TPL -.->|模板来源| RTG
    OUT -->|cargo build --release| BIN["桌面宠物可执行文件"]

    style IMG fill:#e1f5fe
    style BIN fill:#e8f5e9
    style TPL fill:#f3e5f5
    style DOC fill:#fff9c4
```

**两个可交付物**：Python 侧交付「生成能力」，Rust 侧交付「运行时体验」。二者唯一的强耦合是
[生成器 ↔ 运行时契约](#生成器--运行时契约)（两个常量声明 + manifest 格式），其余全部通过数据驱动解耦。

---

## 核心管线流程

```mermaid
flowchart TD
    INPUT["输入图片"] --> S0["Stage 0: Classifier<br/>AI 体型分类"]
    S0 --> S1["Stage 1: Standardizer<br/>分类感知标准化"]
    S1 --> S2["Stage 2: PoseGenerator<br/>尾帧/姿态生成（并发）"]
    S2 --> S3["Stage 3: VideoGenerator<br/>过渡视频生成（并发）"]
    S3 --> S4["Stage 4: FrameExtractor<br/>视频抽帧 (ffmpeg)"]
    S4 --> S5["Stage 5: BackgroundRemover<br/>U2-Net / RMBG 去背景"]
    S5 --> S6["Stage 6: SpritePacker<br/>Sprite Sheet + manifest"]
    S6 --> S7["Stage 7: RuntimeGenerator<br/>Rust 项目生成 + 编译"]
    S7 --> OUTPUT["桌面宠物可执行文件"]

    S0 -.->|"--body-type 覆盖<br/>跳过 AI 分类"| S1
    S2 -.->|"--skip-video<br/>2 帧 fallback"| S5
    S7 -.->|"--no-compile<br/>只生成项目"| OUTPUT

    style INPUT fill:#e1f5fe
    style OUTPUT fill:#e8f5e9
    style S0 fill:#fff3e0
    style S3 fill:#fce4ec
    style S7 fill:#f3e5f5
```

**控制流开关**

| 开关 | 效果 |
|------|------|
| `--body-type` | Stage 0 跳过 AI 调用，直接构造 `ClassificationResult` |
| `--skip-video` | 跳过 Stage 3/4，用 `[标准图, 尾帧]` 作 2 帧 fallback |
| `--no-compile` | Stage 7 只生成 Rust 项目目录，不执行 `cargo build` |
| 断点续跑 | 各阶段命中已有产物即跳过（日志显示「缓存命中」），不重复调用 AI API |

---

## 生成器模块依赖

```mermaid
flowchart LR
    CLI["cli.py<br/>参数解析 + 调度"] --> SETTINGS["config/settings.py<br/>聚合配置中心"]
    CLI --> PIPELINE["pipeline.py<br/>管线编排器"]

    PIPELINE --> STAGES["stages/<br/>7 个阶段实现"]
    PIPELINE --> SETTINGS
    PIPELINE --> ACTIONS["config/actions/<br/>动作集注册表"]

    STAGES --> PROVIDERS["providers/<br/>AI 服务抽象层"]
    STAGES --> PROMPTS["prompts/<br/>模板库"]

    PROVIDERS --> SETTINGS
    PROMPTS --> ACTIONS

    PIPELINE --> RUNTIME["runtime_gen/<br/>Rust 项目生成"]
    RUNTIME --> SETTINGS

    subgraph "配置层"
        SETTINGS
        ACTIONS
    end
    subgraph "服务抽象层"
        PROVIDERS
    end
    subgraph "业务逻辑层"
        STAGES
        PROMPTS
    end
    subgraph "产物生成层"
        RUNTIME
    end

    style CLI fill:#e3f2fd
    style SETTINGS fill:#fff9c4
    style PIPELINE fill:#e8f5e9
    style PROVIDERS fill:#fce4ec
```

**依赖方向原则**：上层依赖下层，同层不互相依赖。`pipeline.py` 通过延迟导入解耦各 Stage，
使单个阶段可以独立测试。

---

## 数据流

```mermaid
flowchart LR
    A["输入图片<br/>Path"] --> B["Stage 0"]
    B -->|"ClassificationResult<br/>{body_type, confidence, material, style}"| C["Stage 1"]
    C -->|"标准化 PNG<br/>Path"| D["Stage 2"]
    D -->|"dict[action, Path]<br/>尾帧集"| E["Stage 3"]
    E -->|"dict[action, Path]<br/>MP4 集"| F["Stage 4"]
    F -->|"dict[action, list[Path]]<br/>帧序列"| G["Stage 5"]
    G -->|"dict[action, list[Path]]<br/>透明帧序列"| H["Stage 6"]
    H -->|"manifest.json + sheets"| I["Stage 7"]
    I -->|"Rust 项目 / 二进制"| J["产物"]

    style A fill:#e1f5fe
    style J fill:#e8f5e9
```

产物目录按阶段编号落盘（`00_classification/` … `06_sprites/`），任何阶段都能单独复查与续跑。

---

## Provider 体系

```mermaid
classDiagram
    class GenerationResult {
        +bool success
        +list~Path~ output_paths
        +str error
        +dict metadata
        +first_path: Path
    }
    class ImageGenProvider {
        <<abstract>>
        +generate(prompt, output_dir, ...) GenerationResult
        +edit(image_paths, prompt, output_dir, ...) GenerationResult
        +supports_edit: bool
    }
    class VideoGenProvider {
        <<abstract>>
        +image_to_video(first_frame, output_dir, *, last_frame, ...) GenerationResult
        +text_to_video(prompt, output_dir, ...) GenerationResult
        +supports_last_frame: bool
    }
    class VisionProvider {
        <<abstract>>
        +describe(image_path, prompt) str
        +classify(image_path, system_prompt, user_prompt) dict
    }
    class AzureGptImageProvider
    class BailianImageProvider
    class KlingVideoProvider
    class BailianVideoProvider
    class OpenAICompatibleVisionProvider

    ImageGenProvider <|-- AzureGptImageProvider
    ImageGenProvider <|-- BailianImageProvider
    VideoGenProvider <|-- KlingVideoProvider
    VideoGenProvider <|-- BailianVideoProvider
    VisionProvider <|-- OpenAICompatibleVisionProvider
    ImageGenProvider ..> GenerationResult : returns
    VideoGenProvider ..> GenerationResult : returns
```

Provider 通过名称注册表 + 延迟导入选择实现，新增 Provider 见
[standards/EXTEND_MECHANISMS.md](standards/EXTEND_MECHANISMS.md)。

---

## 运行时架构

### 模块分层

```mermaid
flowchart TB
    subgraph L0["入口与配置"]
        MAIN["main.rs<br/>嵌入资产 / 解码 / 插件装配"]
        CONFIG["config.rs<br/>唯一调参面（几何/阈值/时长/数值）"]
    end

    subgraph L1["平台层"]
        WINDOW["window.rs<br/>透明置顶窗口 + WindowAnchor(物理像素)"]
        TRAY["tray.rs<br/>可选系统托盘 (feature=tray)"]
    end

    subgraph L2["输入层"]
        INTER["interaction.rs<br/>拖动 / alpha 命中测试 / squash"]
        UIM["ui/menu.rs<br/>光标锚定动作菜单"]
    end

    subgraph L3["意图总线"]
        CMD["command.rs<br/>PetCommand + 唯一执行器 + Notice"]
    end

    subgraph L4["领域层"]
        ANIM["animation.rs<br/>AnimState / 状态机 / 帧播放"]
        PET["pet.rs<br/>生命值 + 心情"]
        BEH["behavior.rs<br/>自主行为"]
        ACH["achievements.rs<br/>成就"]
    end

    subgraph L5["表现层"]
        HUD["ui/hud.rs<br/>生命值 + 当前状态"]
        TOAST["ui/toast.rs<br/>瞬时通知"]
        THEME["ui/theme.rs + ui/icons.rs<br/>设计令牌 + 几何图标"]
    end

    MAIN --> WINDOW & INTER & CMD & ANIM & PET & BEH & ACH & TRAY
    MAIN --> HUD
    CONFIG -.->|常量| INTER & ANIM & PET & BEH & UIM & TOAST & WINDOW
    INTER -->|PetCommand| CMD
    UIM -->|PetCommand| CMD
    TRAY -->|PetCommand| CMD
    CMD --> PET
    CMD --> ANIM
    CMD --> ACH
    CMD -->|Notice| TOAST
    ACH -->|Notice| TOAST
    BEH --> ANIM
    PET --> ANIM
    ANIM --> HUD
    INTER -.->|读取 WindowAnchor| WINDOW
    THEME -.-> UIM & HUD & TOAST

    style CMD fill:#fff3e0
    style CONFIG fill:#fff9c4
```

**关键解耦点**：任何输入面（精灵点击、右键菜单、系统托盘、未来的快捷键/IPC）都**只发
`PetCommand` 消息**，由 `command.rs` 的唯一执行器落实效果。新增输入面无需了解生命值与状态机；
新增规则只改一处。

### 帧内系统流水线

`main.rs` 用 `configure_sets(Update, (...).chain())` 显式固化每帧顺序，避免隐式调度歧义：

```mermaid
flowchart LR
    W["WindowAnchorSystems<br/>刷新窗口物理位置"]
      --> I["InteractionSystems<br/>指针 → 意图 / 拖动 / squash"]
      --> UI["PetUiSystems::Input<br/>菜单定位 + 行激活"]
      --> C["CommandSystems<br/>应用意图（生命值/状态机/成就）"]
      --> B["BehaviorSystems<br/>静息时触发自主动作"]
      --> A["AnimationSystems<br/>帧推进 + action 倒计时"]
      --> P["PetUiSystems::Present<br/>HUD 刷新 + Toast 生命周期"]
```

### 动画状态机

三层覆盖模型，渲染优先级 `drag > action > base`：

```mermaid
stateDiagram-v2
    [*] --> Base

    state Base {
        [*] --> Idle
        Idle --> Sleepy : energy < 25 且 Sleepy 可用
        Idle --> Hungry : hunger > 75 且 Hungry 可用
        Sleepy --> Idle : 恢复
        Hungry --> Idle : 喂食
    }

    Base --> Action : play_action(state, duration)
    Action --> Base : 倒计时归零 / 帧播完 / 看门狗超时
    Action --> Drag : 按住并越过阈值
    Base --> Drag : 按住并越过阈值
    Drag --> Base : 释放

    note right of Action
      循环 sheet 必带 Some(duration)
      非循环 sheet 可用 None（播完即止）
      看门狗 ACTION_WATCHDOG_SECS 兜底
    end note
```

| 机制 | 作用 |
|------|------|
| 可用性感知（`AnimationAssets.available`） | mood→base、菜单项、自主行为候选全部与「实际解码成功的状态集」取交集，运行时永不硬编码 body_type |
| action 时长（`tick_action_duration`） | 循环动画倒计时回落，非循环动画播完回落，另有看门狗防止损坏 sheet 卡死 |
| 静息判定（`behavior::is_resting`） | 判据是「无 action 且未拖动」，**不要求 base == Idle**，因此 Sleepy/Hungry 心情下自主行为依旧工作 |
| 拖动冻结 | 只有当宠物确实拥有 `Drag` sheet 时才冻结帧推进，否则继续播放回落动画 |

### 指针交互与窗口拖动

窗口位置写入 `Window::position`（`WindowPosition::At`，**物理像素**），因此拖动全程只用物理像素：

```mermaid
sequenceDiagram
    participant OS as 操作系统/winit
    participant WA as window.rs::WindowAnchor
    participant PT as interaction.rs::pointer_system
    participant SM as animation.rs::AnimStateMachine
    participant CB as command.rs

    Note over WA: 启动：按主显示器右下角<br/>显式 WindowPosition::At
    OS-->>WA: WindowMoved(physical) 持续校正

    PT->>PT: 左键按下 → 记录 grab（窗口内物理光标位置）
    PT->>PT: alpha 命中测试（非宠物像素直接忽略）
    loop 按住期间每帧
        PT->>PT: delta = cursor_now - grab
        alt delta 越过 DRAG_THRESHOLD
            PT->>SM: dragging = true（Drag 姿态）
            PT->>WA: anchor += delta
            PT->>OS: WindowPosition::At(anchor)
            Note over PT,OS: 窗口跟随后光标回到 grab，<br/>因此 delta 天然是每帧增量（自校正）
        end
    end
    PT->>PT: 释放
    alt 从未越过阈值
        PT->>CB: PetCommand::Pet（抚摸）
    else 是真实拖动
        PT->>SM: dragging = false
    end
```

设计要点：

- **不使用 `MouseMotion`**：macOS 上它是逻辑点、Windows 上是原始设备增量，与物理像素窗口位置混用必然漂移。
- **只有按在宠物身上才可拖动**：透明边缘的按下被忽略，不会「拖到空气」。
- **UI 优先**：`ui::UiBlocker` 标记的区域（菜单、HUD）吞掉指针事件，菜单点击永不穿透到宠物。
- **菜单外点击关闭菜单**，且该次点击被消费（不会顺带抚摸）。

### Overlay UI

| 表面 | 位置 | 说明 |
|------|------|------|
| 动作菜单 | 右键光标处，夹取进窗口 | 数据驱动：护理项（Feed/Play）+ 每个可用动画一行 + Sleep（有 sheet 时）+ Quit；上限 `MAX_MENU_ITEMS` |
| 状态 HUD | 左下 | `NRG / HAP / HGR` + 当前生效状态名（便于验证状态机） |
| Toast | 顶部居中 | 动作反馈与成就解锁，最多 3 条，末段淡出 |

**ASCII-only 硬约束**：Bevy 内嵌默认字体 `FiraMono-subset.ttf` 的 cmap 只有 95 个码位
（`U+0020..U+007E`），任何 emoji / `✕` / `•` / CJK 都会渲染成方块。因此 UI 文案一律 ASCII，
图标由 `ui/icons.rs` 用 UI 节点（矩形/圆/旋转条，`UiTransform` 支持旋转）组合绘制，
零字体依赖、零外部资产。完整规则见 [standards/RUNTIME_UX.md](standards/RUNTIME_UX.md)。

---

## 生成器 ↔ 运行时契约

权威定义见 **[standards/GENERATOR_RUNTIME_CONTRACT.md](standards/GENERATOR_RUNTIME_CONTRACT.md)**（单一事实源）。
要点：

- 模板 `main.rs` 中两处 `// GENERATOR-CONTRACT:` 锁定声明（`SPRITE_SHEETS` 5 元组、`FRAME_SIZE`）
  由生成器正则 patch，断言 `count == 1`；
- `AnimState` 白名单 29 变体，生成前 fail-fast；
- manifest 字段与 `frame_count` 自检；
- 除这两处常量外，模板可以自由重构 —— `tests/test_runtime_gen_contract.py::test_generate_from_real_template`
  会用真实模板端到端生成一次，守护「模板目录结构 + patch 正则」始终一致。

---

## 设计原则

| 原则 | 实现方式 |
|------|---------|
| **模块化解耦** | Python：Stage 独立文件 + 延迟导入；Rust：一职责一模块 + 插件装配 + 消息总线 |
| **数据驱动** | 动画集/时长/菜单项全部来自 manifest 与 `available` 集，运行时不硬编码 body_type |
| **Provider 抽象** | 3 套抽象基类 + 名称注册表，AI 服务可切换 |
| **配置聚合** | Python `Settings` 单一事实源；Rust `config.rs` 单一调参面 |
| **容错降级** | `GenerationResult` 不抛异常；解码失败回落 Idle/fallback 图；状态机看门狗 |
| **零文件写入** | 运行时不写盘，资产 `include_bytes!` 编译期内嵌，状态纯内存 |
| **可观测** | 管线阶段化落盘 + 缓存命中日志；运行时 HUD 显示当前状态、Toast 显示反馈 |

---

## 错误处理策略

| 场景 | 策略 | 位置 |
|------|------|------|
| AI 服务调用失败 | `GenerationResult(success=False, error=...)`，不抛异常 | `providers/base.py` |
| 分类器低置信度 | 低于 `confidence_threshold` 用默认体型 | `stages/classifier.py` |
| 异步任务超时 | `task_timeout` / `poll_interval` 控制轮询 | `config/settings.py` |
| 跳过视频 | 2 帧 fallback 保证管线跑通 | `pipeline.py` |
| 非法 AnimState | 生成前白名单 fail-fast | `runtime_gen/rust_project.py` |
| 找不到标准图 | 保留模板 fallback.png 并 warning | `runtime_gen/rust_project.py` |
| Rust 编译失败 | `RuntimeError` 携带 cargo stderr | `runtime_gen/compiler.py` |
| sheet 解码失败 | `warn` 跳过该动画；无 Idle 时用 fallback 图 | `main.rs::load_animations` |
| 缺失动画状态 | `animate_sprite` 回落 Idle | `animation.rs` |
| action 永不结束 | `ACTION_WATCHDOG_SECS` 强制清除 | `animation.rs` |
| 窗口位置未知 | 拖动跳过移动但不 panic（`WindowAnchor::offset` 返回 `Option`） | `window.rs` / `interaction.rs` |

---

## 扩展点索引

| 我要… | 看这里 |
|-------|--------|
| 新增一个动作 | [standards/EXTEND_ACTIONS.md](standards/EXTEND_ACTIONS.md) |
| 新增体型 / Provider / 管线阶段 / 运行时系统 | [standards/EXTEND_MECHANISMS.md](standards/EXTEND_MECHANISMS.md) |
| 改提示词 | [standards/EXTEND_PROMPTS.md](standards/EXTEND_PROMPTS.md) |
| 改 UI / 交互 | [standards/RUNTIME_UX.md](standards/RUNTIME_UX.md) |
| 改跨语言常量 | [standards/GENERATOR_RUNTIME_CONTRACT.md](standards/GENERATOR_RUNTIME_CONTRACT.md) |
| 提交前要跑什么 | [standards/CODE_QUALITY_GATES.md](standards/CODE_QUALITY_GATES.md) |
