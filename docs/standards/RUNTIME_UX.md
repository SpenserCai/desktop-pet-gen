# 运行时交互与 UI 规范

> 适用范围：`pet-runtime/src/{window,interaction,ui/*}.rs` 及其生成副本。
> 这些规则来自真实缺陷，违反其中任何一条都会退回已修复过的问题。

## 一、字体：ASCII-only（硬约束）

**事实**：Bevy 内嵌的默认字体是 `bevy_text/src/FiraMono-subset.ttf`，其 cmap 只包含
**95 个码位，最大 `U+007E`**（可实测：解析该 TTF 的 cmap）。

**后果**：任何非 ASCII 字符——emoji（`🍖😴💃👋`）、`✕`(U+2715)、`•`(U+2022)、`▶`(U+25B6)、
CJK——都没有字形，渲染为 tofu 方块。这正是「菜单图标全是方块」的根因。

**规则**

1. 所有进入 UI 的字符串字面量必须是 ASCII（注释与测试段不受限制）。
2. 图标**不用字形**：由 `ui/icons.rs` 用 UI 节点组合绘制（矩形 / 圆角 / 圆 / 旋转条，
   `UiTransform::from_rotation` 提供旋转），零字体依赖、零外部资产、跨平台一致。
3. 新增图标 = 在 `IconKind` 加变体 + 在 `shapes` 模块加形状表 + 在 `accent()` 加配色 +
   （如与动画相关）在 `IconKind::for_state` 加映射。形状坐标必须落在 `ICON_SIZE²` 盒子内
   （由 `every_icon_has_shapes_inside_its_box` 守护）。
4. 若将来确实要用 emoji：需embed 一个可再发布的字体（`Font::try_from_bytes` + `Assets<Font>`，
   仍满足零文件写入），并且必须离线核验该字体 cmap 覆盖所用码位；在此之前不得引入 emoji 文案。

守护：`tests/test_runtime_gen_contract.py::test_template_ui_text_is_ascii_only`、
`menu_labels_are_ascii_only`、`field_text_is_ascii_and_labelled`、`notice_text_is_ascii`。

## 二、窗口与坐标系

| 量 | 单位 | 来源 |
|----|------|------|
| `Window::position = WindowPosition::At(IVec2)` | **物理像素** | bevy_winit 转成 `PhysicalPosition` |
| `WindowMoved.position` | **物理像素** | OS 事件（权威） |
| `Window::physical_cursor_position()` | **物理像素**，原点为窗口左上 | CursorMoved |
| `Window::width()/height()`、`Val::Px`、`Node` 尺寸 | **逻辑像素** | `physical / scale_factor` |
| `ComputedNode::size` | **物理像素** | 布局结果 |
| `WindowResolution::new(w, h)` | 创建时按**逻辑**尺寸请求 | bevy_winit 传给 winit 的 `LogicalSize` |

**规则**

1. 窗口移动只用物理像素，且必须以 `WindowAnchor` 为唯一位置事实源。
   禁止直接读 `Window::position` 做增量（初始为 `Automatic`，读不到值 —— 这就是「无法拖动」的根因）。
2. **禁止用 `MouseMotion` 驱动窗口移动**：macOS 上它是 `NSEvent.deltaX/Y`（逻辑点），
   Windows 上是 raw input 设备增量。与物理像素窗口位置混用必然按 `scale_factor` 漂移。
   正确做法是「窗口内物理光标位置 − 抓取点」，窗口跟随后光标自然回到抓取点，形成自校正闭环。
3. 逻辑↔物理换算一律用 `window.scale_factor().max(0.1)`，不得假设 1.0。
4. 启动位置由 `window::initial_position` 计算（主显示器右下角内缩），可单测。
5. **透明覆盖窗口必须 `has_shadow: false`**（Bevy 默认 `true`）。macOS 依据窗口的
   alpha 轮廓生成投影并**缓存**它；桌宠的轮廓每帧都在变，缓存下来的旧轮廓投影会以
   灰色描边的形式留在屏幕上，看起来像"上一个动作的残影"。
   由 `window::tests::primary_window_is_a_shadowless_transparent_overlay` 守护。

**排查提示**：见到"上一个姿态的灰色描边"时，先区分是**素材**问题还是**窗口**问题 ——
统计 sheet 各帧的半透明像素占比，正常抗锯齿边缘只占约 0.5%（256² 的主体周长量级）；
明显超出才说明抠图残留，否则就要往窗口合成/投影方向查。

## 三、指针语义

| 输入 | 行为 |
|------|------|
| 左键按在宠物**不透明像素**上并越过 `DRAG_THRESHOLD` | 拖动窗口 + `Drag` 姿态 + squash 反馈 |
| 左键按在宠物上、位移未越阈值 | 抚摸（`PetCommand::Pet`） |
| 左键按在透明边缘 / `UiBlocker` 区域 | 忽略（既不拖动也不抚摸） |
| 菜单打开时左键点菜单外 | 关闭菜单，且该次点击被消费 |
| 右键 | 在光标处开/关菜单 |

**规则**

1. 抚摸必须做 **alpha 命中测试**（`ALPHA_HIT_THRESHOLD`）：先包围盒，再采样当前帧像素。
   取不到像素数据时退化为包围盒命中（永不误伤可用性）。
   这依赖 `RenderAssetUsages::default()` 保留主世界像素 —— 改解码路径时不要丢掉它。
2. 交互式 UI 根节点必须挂 `ui::UiBlocker`；非交互表面（Toast）**不要**挂，否则会吞掉点击。
3. 菜单用 `Visibility::Hidden` 隐藏而非 `Display::None`：隐藏时仍参与布局，
   `ComputedNode::size` 可用于夹取定位，且 Bevy 会把隐藏节点的 `Interaction` 置 `None`（不可点）。
4. 释放事件里必须无条件清 `dragging` 与 `speed`，防止焦点被抢导致姿态卡住。

## 四、菜单

1. **数据驱动**：护理项（Feed/Play）+ `ACTION_ORDER ∩ available` 每项一行 + `Sleep`（有 sheet 时）+ `Quit`。
   不得硬编码体型专属项。
2. **两行不同文案不得映射到同一动画**：这会让用户觉得「点了都只有 Happy」。
   新增护理项时要么给它独立动画，要么用 Toast 明确区分反馈。
3. **必须夹取进窗口**：`clamp_menu_position`，并对「面板比窗口还大」的极端情况退化到原点。
4. **行数上限** `MAX_MENU_ITEMS`，且 `estimated_size(MAX_MENU_ITEMS).y < WINDOW_SIZE`（有单测守护）。
   加行 / 加字号前先确认这条不等式仍成立，否则加大 `WINDOW_SIZE`。

## 五、反馈可见性

GUI 应用从 Finder / 资源管理器启动时看不到 stdout，所以：

1. 用户可感知的事件（成就解锁、动作确认）必须走 `Notice` → Toast 上屏；`println!` 只作为日志镜像。
2. HUD 必须显示当前生效状态名，用于人工验证状态机。
3. 频繁事件（抚摸）不发 Toast，避免刷屏。

## 六、渲染

1. `ImagePlugin::default()`（线性过滤）：`FRAME_SIZE²` 帧被绘制到 `SPRITE_SIZE` 逻辑像素
   （HiDPI 下约 1.6× 放大），nearest 会出现明显锯齿。
   若追求像素风或 1:1 采样，改 `SPRITE_SIZE` 或用 `--frame-size 512` 重打包，而不是退回 nearest。
2. 透明窗口三件套不得改动：`ClearColor(Color::NONE)`、`Camera2d`、平台对应的
   `CompositeAlphaMode`（macOS `PostMultiplied` / Linux `PreMultiplied` / Windows `Auto`）。
3. sheet 必须 CPU 逐帧切片（每帧 ≤ `FRAME_SIZE`），避免超宽纹理触发 GPU 上限。

## 七、新增输入面的正确姿势

新的输入方式（快捷键、托盘项、IPC…）**只发 `PetCommand`**，不直接改 `Pet` / `AnimStateMachine`：

```rust
fn my_input_surface(mut commands: MessageWriter<PetCommand>, /* ... */) {
    commands.write(PetCommand::Feed);
}
```

并把系统放进 `CommandSystems` 之前的集合里（例如 `InteractionSystems` 或 `PetUiSystems::Input`），
这样意图能在同一帧生效。规则细节见 [EXTEND_MECHANISMS.md](EXTEND_MECHANISMS.md)。
