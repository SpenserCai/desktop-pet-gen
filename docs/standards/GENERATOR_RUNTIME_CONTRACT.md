# 生成器 ↔ 运行时契约（单一事实源 / Single Source of Truth）

> 本文档是 Python 生成器（`pet_generator/`）与 Rust 运行时模板（`pet-runtime/`）之间
> **唯一的跨语言强耦合**定义。
> 契约文本必须逐字一致（含空格、标点、注释措辞），否则生成器正则无法匹配模板，端到端生成失败。
> **若必须变更契约：先改本文档，再改两侧代码，并同步契约回归测试。**

契约只覆盖下面四项。模板 `src/` 的其他部分（模块划分、文件增删、系统组织）**可以自由重构**，
生成器整目录复制模板，`tests/test_runtime_gen_contract.py::test_generate_from_real_template`
会用真实模板端到端生成一次，守护「目录结构 + patch 正则」始终自洽。

---

## 1. SPRITE_SHEETS 常量（5 元组）

### 1.1 Rust 类型

```
&[(AnimState, &[u8], f32, bool, f32)]
```

五位含义：`(状态, PNG字节, fps, 是否循环, duration_secs)`。

- `duration_secs`：该动作的建议播放时长（秒），来自 manifest 各 action 的 `duration_secs`。
  运行时把 `> 0` 的值存入 `SpriteAnimation.default_duration: Option<f32>`：
  循环动画用它作为 action overlay 的回落倒计时；非循环动画播完即止。

### 1.2 模板 `pet-runtime/src/main.rs` 中的**精确声明文本**

```rust
// GENERATOR-CONTRACT: DO NOT EDIT — kept in sync by pet_generator/runtime_gen/rust_project.py
const SPRITE_SHEETS: &[(AnimState, &[u8], f32, bool, f32)] = &[
    // Generator will insert entries here
];
```

### 1.3 生成器 patch 后（示例）

```rust
// GENERATOR-CONTRACT: DO NOT EDIT — kept in sync by pet_generator/runtime_gen/rust_project.py
const SPRITE_SHEETS: &[(AnimState, &[u8], f32, bool, f32)] = &[
    (AnimState::Idle, include_bytes!("../assets/idle_sheet.png"), 12.0, true, 3.0),
    (AnimState::Wave, include_bytes!("../assets/wave_sheet.png"), 12.0, false, 2.0),
];
```

替换时**必须保留** `// GENERATOR-CONTRACT:` 锁定注释行。

### 1.4 doc-comment 示例（main.rs 顶部文档注释，须与 5 元组同步）

```rust
/// const SPRITE_SHEETS: &[(AnimState, &[u8], f32, bool, f32)] = &[
///     (AnimState::Idle,  include_bytes!("../assets/idle.png"),  8.0, true,  3.0),
///     (AnimState::Happy, include_bytes!("../assets/happy.png"), 10.0, false, 1.5),
/// ];
```

正则锚定锁定注释 + `const` 行的相邻关系，所以 doc-comment 里的同形文本不会被误伤
（由 `test_patch_sprite_sheets_5tuple` 断言）。

### 1.5 patch 正则（必须能匹配 §1.2，`count == 1`）

```python
pattern = (
    r"// GENERATOR-CONTRACT: DO NOT EDIT[^\n]*\n"
    r"const SPRITE_SHEETS: &\[\(AnimState, &\[u8\], f32, bool, f32\)\] = &\[.*?\];"
)
```

替换文本（含锁定注释行）：

```python
replacement = (
    "// GENERATOR-CONTRACT: DO NOT EDIT — kept in sync by pet_generator/runtime_gen/rust_project.py\n"
    "const SPRITE_SHEETS: &[(AnimState, &[u8], f32, bool, f32)] = &[\n"
    f"{entries_text}\n"
    "];"
)
```

`re.subn(...)` 的 `count` 必须等于 1，否则抛 `RuntimeError`。

---

## 2. FRAME_SIZE 常量

### 2.1 模板中的**精确声明文本**（注释行与 const 行必须相邻）

```rust
// GENERATOR-CONTRACT: DO NOT EDIT — patched from manifest.frame_size by the generator
const FRAME_SIZE: u32 = 256;
```

### 2.2 patch 正则

```python
frame_pattern = (
    r"(// GENERATOR-CONTRACT: DO NOT EDIT — patched from manifest\.frame_size by the generator\n"
    r"const FRAME_SIZE: u32 = )\d+(;)"
)
# 替换为 rf'\g<1>{manifest["frame_size"]}\g<2>'，断言 count == 1
```

manifest 无 `frame_size` 字段时默认 256 且不改动（向后兼容）。

运行时用 `FRAME_SIZE` 做 CPU 逐帧切片（`cols = sheet_width / FRAME_SIZE`），
因此它必须与打包时的帧尺寸一致，否则动画错乱。

---

## 3. AnimState 白名单（29 变体，body-type-agnostic 全集）

生成前 fail-fast：每个 action 解析出的 `rust_variant` 必须 ∈ 以下白名单。

```
Idle, Happy, Sleep, Drag,
Sleepy, Hungry, Dance, Wave, Yawn, Stretch, LookAround,
TailWag, Walk, Run, Sit, Pounce, TiltHead, Scratch,
Bounce, Squish, StretchVertical, Float, Spin, Wobble,
Glow, Shake, Tilt, BounceSmall, Sparkle
```

- 维护位置：`pet_generator/runtime_gen/rust_project.py` 顶部常量 `KNOWN_ANIM_STATES: frozenset[str]`。
- 它是运行时 `animation.rs::AnimState` 枚举的镜像 —— 新增变体必须**同时**更新两处。
- 校验失败时抛出含「非法 variant + action 名 + body_type」的错误，在编译前阻断。
- `snake_to_pascal` 推导不出目标名时，在 `ANIM_STATE_MAP` 里加显式映射。

---

## 4. Manifest 契约（SpritePacker 产出）

```json
{
  "pet_name": "...",
  "body_type": "humanoid|quadruped|limbless|object",
  "frame_size": 256,
  "actions": {
    "<action_name>": {
      "file": "<action>_sheet.png",
      "frame_count": 12,
      "fps": 12,
      "loop": true,
      "duration_secs": 3.0
    }
  }
}
```

- `frame_count` 自检：打包后断言 `sheet_width // frame_size == frame_count`，不符 fail-fast。
- `duration_secs` 缺失时，生成器按 `frame_count / fps` 兜底。
- `loop` 直接决定运行时的回落方式（循环 → 倒计时；非循环 → 播完即止）。

---

## 5. 生成器对模板目录的隐式约定

除上述常量外，生成器还依赖以下目录约定（同样受回归测试守护）：

| 约定 | 说明 |
|------|------|
| 模板整目录可复制 | `shutil.copytree`，排除 `target/`、`.DS_Store`、`.git`；`src/` 下的子目录（如 `src/ui/`）会一并复制 |
| `Cargo.toml` 首个 `name = "..."` 可替换 | 生成器改写为 `pet_name` |
| `assets/` 目录存在 | sprite sheets 复制进去；`fallback.png` 可被标准图覆盖 |
| `assets/fallback.png` 必须存在 | 运行时 `include_bytes!` 依赖它（无 Idle sheet 时的降级路径） |
| 标准图查找路径 | `<sprite_dir>/../01_standard` 优先，其次 `../../01_standard`，目录内约定名优先、否则取最新 PNG |

---

## 6. 设计原则（不得回退）

1. **body-type-agnostic**：运行时永不硬编码 body_type；"用可用的动画"。
2. **数据驱动**：动画选择、时长、菜单项都来自 manifest 与 `available` 集，不是代码分支。
3. **零文件写入**：运行时不写盘；资产 `include_bytes!` 编译期内嵌；状态纯内存。
4. **错误降级**：解码返回 `Option`，不 panic；缺失状态回落 `Idle`；无 Idle 时用 fallback 图。
5. **保留既有优势**：29 个 AnimState、CPU 逐帧切片（免疫 GPU 纹理上限）、`skip_taskbar`、
   透明窗口三件套（`ClearColor(Color::NONE)` + `Camera2d` + 平台 `CompositeAlphaMode`）。
6. **纹理过滤 = 线性**（`ImagePlugin::default()`）：`FRAME_SIZE²` 的帧被绘制到 `SPRITE_SIZE`
   逻辑像素，HiDPI 下约 1.6× 放大，`default_nearest()` 会产生明显锯齿。
   需要 1:1 采样时改 `SPRITE_SIZE` 或用 `--frame-size 512` 重打包，而不是退回 nearest。

---

## 7. 契约回归测试

`tests/test_runtime_gen_contract.py` 覆盖：

| 测试 | 守护 |
|------|------|
| `test_patch_sprite_sheets_5tuple` | §1.2/§1.5 逐字一致 + `count==1` + doc-comment 不被误伤 |
| `test_duration_secs_fallback_from_frame_count` | §4 `duration_secs` 兜底 |
| `test_patch_frame_size_512` / `_missing_keeps_default` / `_count_must_be_one` | §2 |
| `test_whitelist_failfast` / `test_whitelist_validator_direct` / `test_all_body_type_variants_known` | §3 |
| `test_frame_count_mismatch` / `test_frame_count_match_passes` / `test_pack_all_end_to_end_selfcheck` | §4 自检 |
| `test_generate_from_real_template` | §5 真实模板端到端（含 `src/ui/` 子模块复制） |
| `test_fallback_uses_standard_image_from_sibling_dir` / `_keeps_template_when_no_standard_image` | §5 fallback 查找 |
| `test_template_ui_text_is_ascii_only` | 运行时 UI 文案 ASCII-only（见 RUNTIME_UX.md） |
