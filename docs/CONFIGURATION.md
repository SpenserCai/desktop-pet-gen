# 配置参考文档

> desktop-pet-gen v0.1.0 — 配置体系完整参考

## 目录

- [配置优先级](#配置优先级)
- [Settings 字段参考](#settings-字段参考)
- [环境变量完整列表](#环境变量完整列表)
- [CLI 参数完整列表](#cli-参数完整列表)
- [运行时配置（config.rs）](#运行时配置configrs)
- [配置文件（未来）](#配置文件未来)
- [UI 扩展预留](#ui-扩展预留)

---

## 配置优先级

配置值按以下优先级从高到低解析，高优先级覆盖低优先级：

```
CLI 参数  >  环境变量  >  配置文件(未来)  >  代码默认值
```

**实现机制：**

1. `Settings.from_env()` 从环境变量加载，未设置的字段保留默认值
2. `build_settings(args)` 将 CLI 参数逐一覆盖到 Settings 实例（仅当用户显式传入时）
3. 未来 `Settings.from_file(path)` 将从 JSON 配置文件加载，优先级介于环境变量与默认值之间

```python
# 优先级示意
settings = Settings.from_env()  # 环境变量 > 默认值
if args.name is not None:  # CLI > 环境变量
    settings.pet_name = args.name
```

---

## Settings 字段参考

### 顶层字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `pet_name` | `str` | `"my-pet"` | 宠物项目名称（用于输出目录与 manifest） |
| `body_type_override` | `str \| None` | `None` | 手动指定体型，跳过 AI 分类。可选值: `humanoid` / `quadruped` / `limbless` / `object` |
| `selected_actions` | `list[str] \| None` | `None` | 动作子集白名单，`None` 表示生成全部动作 |

### ClassifierSettings（分类器配置）

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model` | `str` | `"qwen3.7-plus"` | 视觉分类模型名称 |
| `api_base` | `str` | `"https://dashscope.aliyuncs.com/compatible-mode/v1"` | API base URL |
| `api_key_env` | `str` | `"DASHSCOPE_API_KEY"` | API Key 对应的环境变量名 |
| `temperature` | `float` | `0.1` | 生成温度（低温度 = 更确定性分类） |
| `max_tokens` | `int` | `1024` | 最大输出 token 数 |
| `max_retries` | `int` | `2` | 失败重试次数 |
| `confidence_threshold` | `float` | `0.7` | 置信度阈值，低于此值使用默认体型 |
| `timeout` | `int` | `60` | 单次请求超时（秒） |

**派生属性：**
- `api_key` → 从 `os.environ[api_key_env]` 读取

### ProviderSettings（Provider 选择与凭据）

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `image_provider` | `str` | `"azure"` | 图像 Provider: `"azure"` \| `"bailian"` |
| `video_provider` | `str` | `"kling"` | 视频 Provider: `"kling"` \| `"wan27"` |
| `azure_api_key_env` | `str` | `"AZURE_OPENAI_API_KEY"` | Azure API Key 环境变量名 |
| `azure_endpoint_env` | `str` | `"AZURE_OPENAI_ENDPOINT"` | Azure 端点环境变量名 |
| `azure_api_version` | `str` | `"2025-04-01-preview"` | Azure API 版本 |
| `azure_model` | `str` | `"gpt-image-2"` | Azure 图像模型 |
| `dashscope_api_key_env` | `str` | `"DASHSCOPE_API_KEY"` | 百炼 API Key 环境变量名 |
| `dashscope_base_url` | `str` | `"https://dashscope.aliyuncs.com"` | 百炼 base URL |
| `kling_model` | `str` | `"kling/kling-v3-omni-video-generation"` | Kling 视频模型 |
| `wan_i2v_model` | `str` | `"wan2.7-i2v"` | WAN 图生视频模型 |
| `wan_t2v_model` | `str` | `"wan2.7-t2v"` | WAN 文生视频模型 |
| `wan_image_model` | `str` | `"wan2.7-image-pro"` | WAN 图像生成模型 |

**派生属性：**
- `azure_api_key` → 从 `os.environ[azure_api_key_env]` 读取
- `azure_endpoint` → 从 `os.environ[azure_endpoint_env]` 读取
- `dashscope_api_key` → 从 `os.environ[dashscope_api_key_env]` 读取

### PipelineSettings（管线运行参数）

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `frame_size` | `int` | `256` | 精灵图帧尺寸（正方形，像素） |
| `output_dir` | `str` | `"./output"` | 输出根目录 |
| `bg_model` | `str` | `"u2net"` | 去背景模型: `"u2net"`（快速） \| `"rmbg"`（RMBG-2.0，高质量） |
| `skip_video` | `bool` | `False` | 跳过视频生成（用 2 帧 fallback） |
| `no_compile` | `bool` | `False` | 仅生成 Rust 项目，不编译 |
| `debug_build` | `bool` | `False` | Rust debug 模式编译（更快，无优化） |
| `verbose` | `bool` | `False` | 详细日志输出 |
| `fps` | `int` | `12` | 默认帧率 |
| `poll_interval` | `int` | `10` | 异步任务轮询间隔（秒） |
| `task_timeout` | `int` | `600` | 异步任务超时（秒） |

**派生属性：**
- `output_path` → `Path(output_dir)`

---

## 环境变量完整列表

### API 凭据（必需）

| 环境变量 | 用途 | 必需条件 |
|---------|------|---------|
| `AZURE_OPENAI_API_KEY` | Azure GPT-Image-2 图像生成 API Key | `image_provider=azure` 时 |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI 服务端点 URL | `image_provider=azure` 时 |
| `DASHSCOPE_API_KEY` | 百炼 DashScope API Key（分类器 + 百炼 Provider 共用） | 始终需要（分类器） |

### 可选配置

| 环境变量 | 用途 | 默认行为 |
|---------|------|---------|
| `U2NET_MODEL_PATH` | 自定义 U2-Net ONNX 模型路径 | 使用项目内置 `models/u2net.onnx` |
| `RMBG_MODEL_PATH` | 自定义 RMBG-2.0 ONNX 模型路径 | 使用项目内置 `models/rmbg-2.0.onnx` |
| `PET_BG_MODEL` | 去背景模型选择 (`u2net` \| `rmbg`) | `u2net` |

> **去背景模型说明**：两个 ONNX 模型放在 `models/`（`u2net.onnx` 168 MiB / `rmbg-2.0.onnx` 490 MiB，后者是 RMBG-2.0 BiRefNet 的 fp16 变体），**不入版本库**——单文件超 Git 上限。首次使用运行 `python scripts/fetch_models.py` 从 ModelScope 拉取（SHA256 校验 + 断点续传）。模型查找优先级：构造参数 > 环境变量 > 项目 `models/` > 用户主目录（`~/.u2net/`、`~/.rmbg/`）。运行时按 `CUDAExecutionProvider` → `CoreMLExecutionProvider` → `CPUExecutionProvider` 自动探测最优执行后端（EP），不支持的算子自动回落 CPU；实际启用 EP 会记录在日志中。

### 管线行为覆盖

| 环境变量 | 类型 | 说明 |
|---------|------|------|
| `PET_NAME` | `str` | 宠物名称 |
| `PET_IMAGE_PROVIDER` | `str` | 图像 Provider (`azure` \| `bailian`) |
| `PET_VIDEO_PROVIDER` | `str` | 视频 Provider (`kling` \| `wan27`) |
| `PET_FRAME_SIZE` | `int` | 帧尺寸 |
| `PET_OUTPUT_DIR` | `str` | 输出目录 |
| `PET_BODY_TYPE` | `str` | 体型覆盖 |
| `PET_FPS` | `int` | 帧率 |
| `PET_SKIP_VIDEO` | `bool` | 跳过视频 (`1`/`true`/`yes`/`on`) |
| `PET_NO_COMPILE` | `bool` | 跳过编译 (`1`/`true`/`yes`/`on`) |
| `PET_DEBUG_BUILD` | `bool` | Debug 编译 (`1`/`true`/`yes`/`on`) |
| `PET_VERBOSE` | `bool` | 详细日志 (`1`/`true`/`yes`/`on`) |
| `PET_BG_MODEL` | `str` | 去背景模型 (`u2net` \| `rmbg`) |

### 模型分发（scripts/fetch_models.py）

| 环境变量 | 类型 | 说明 |
|---------|------|------|
| `MODELSCOPE_ENDPOINT` | `str` | ModelScope 站点/镜像，默认 `https://www.modelscope.cn` |
| `U2NET_MODEL_PATH` | `str` | 显式指定 u2net 权重路径（优先于项目 `models/`） |
| `RMBG_MODEL_PATH` | `str` | 显式指定 RMBG-2.0 权重路径 |

### 分类器覆盖

| 环境变量 | 类型 | 说明 |
|---------|------|------|
| `CLASSIFIER_MODEL` | `str` | 分类器模型名称 |
| `CLASSIFIER_API_BASE` | `str` | 分类器 API base URL |
| `CLASSIFIER_API_KEY_ENV` | `str` | 分类器 API Key 环境变量名（间接引用） |

---

## CLI 参数完整列表

```
pet-gen --image IMAGE [OPTIONS]
```

### 必选参数

| 参数 | 短写 | 类型 | 说明 |
|------|------|------|------|
| `--image` | `-i` | `Path` | 输入图片路径 |

### 基础参数

| 参数 | 短写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--name` | `-n` | `str` | `my-pet` | 宠物名称 |
| `--output-dir` | `-o` | `str` | `./output` | 输出目录 |

### 分类器参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--classifier-model` | `str` | `qwen3.7-plus` | 分类器模型 |
| `--classifier-base` | `str` | DashScope URL | 分类器 API base URL |
| `--body-type` | `choice` | `None` (AI 分类) | 手动指定体型: `humanoid` \| `quadruped` \| `limbless` \| `object` |

### Provider 选择

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--image-provider` | `choice` | `azure` | 图像 Provider: `azure` \| `bailian` |
| `--video-provider` | `choice` | `kling` | 视频 Provider: `kling` \| `wan27` |

### 动作与帧参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--actions` | `str` | 全部 | 动作子集（逗号分隔，如 `idle,happy,dance`） |
| `--frame-size` | `int` | `256` | 帧尺寸（像素） |

### 去背景参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--bg-model` | `choice` | `u2net` | 去背景模型: `u2net`（快速） \| `rmbg`（RMBG-2.0，高质量） |

### 管线控制

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--skip-video` | `flag` | `False` | 跳过视频生成（用 2 帧 fallback） |
| `--no-compile` | `flag` | `False` | 仅生成 Rust 项目，不编译 |
| `--debug` | `flag` | `False` | Debug 模式编译（更快，无优化） |
| `--verbose` / `-v` | `flag` | `False` | 详细日志输出 |
| `--version` | `flag` | — | 显示版本号 |

---

## 运行时配置（config.rs）

运行时**没有配置文件**（设计约束：零文件写入），所有可调项集中在
`pet-runtime/src/config.rs` 编译期常量里。改这里即可调整手感，不需要翻系统实现。

单位约定：长度为**逻辑像素**（除名字含 `PHYSICAL` 者）、时长为秒、生命值为 `0.0..=100.0`。

### 窗口与精灵几何

| 常量 | 默认 | 说明 |
|------|------|------|
| `WINDOW_SIZE` | `300.0` | 透明覆盖窗口边长。必须容纳菜单：`estimated_size(MAX_MENU_ITEMS).y < WINDOW_SIZE`（有单测守护） |
| `SPRITE_SIZE` | `210.0` | 宠物绘制尺寸 |
| `SPAWN_MARGIN_RIGHT` / `SPAWN_MARGIN_BOTTOM` | `40.0` / `90.0` | 启动时距主显示器右/下边缘的内缩（底部留给 Dock / 任务栏） |

### 指针交互

| 常量 | 默认 | 说明 |
|------|------|------|
| `DRAG_THRESHOLD` | `4.0` | 越过该位移才从"点击"升级为"拖动"（按 `scale_factor` 换算物理像素） |
| `ALPHA_HIT_THRESHOLD` | `0.08` | 命中测试的 alpha 下限，低于它视为"不是宠物" |
| `SQUASH_PER_SPEED` / `SQUASH_MAX` | `0.006` / `0.2` | 拖动挤压拉伸强度与上限 |

### 动作时长

| 常量 | 默认 | 说明 |
|------|------|------|
| `LOOP_ACTION_SECS` | `3.0` | 循环 sheet 未声明 `duration_secs` 时的兜底时长 |
| `HAPPY_SECS` | `1.5` | 抚摸/喂食/玩耍的 Happy 反应兜底时长 |
| `SLEEP_SECS` | `10.0` | 主动 Sleep 时长（Sleep 永远是定时 action，不是常驻 base） |
| `ACTION_WATCHDOG_SECS` | `20.0` | 非循环 action 的看门狗上限，防损坏 sheet 卡死 |
| `BEHAVIOR_FIRST_DELAY_SECS` | `10.0` | 首次自主行为延迟 |
| `BEHAVIOR_INTERVAL_SECS` | `(15.0, 30.0)` | 自主行为间隔随机区间 |

### 生命值经济

| 常量 | 默认 | 说明 |
|------|------|------|
| `ENERGY_DECAY_PER_MIN` | `1.0` | 精力每分钟衰减（满→空 ≈100 分钟） |
| `HAPPINESS_DECAY_PER_MIN` | `1.5` | 快乐每分钟衰减 |
| `HUNGER_GROWTH_PER_MIN` | `2.0` | 饥饿每分钟增长（高饥饿 = 坏） |
| `PET_HAPPINESS_GAIN` | `10.0` | 单次抚摸的快乐增益 |
| `PLAY_HAPPINESS_GAIN` | `20.0` | Play 菜单项的快乐增益 |
| `FEED_HUNGER_RELIEF` | `30.0` | Feed 菜单项缓解的饥饿 |
| `SLEEP_ENERGY_RESTORE` | `40.0` | Sleep 恢复的精力 |

### UI

| 常量 | 默认 | 说明 |
|------|------|------|
| `MENU_WIDTH` / `MENU_ITEM_HEIGHT` | `128.0` / `21.0` | 菜单宽度与行高（用于定位估算） |
| `MAX_MENU_ITEMS` | `12` | 菜单行数硬上限，超出的动作行被丢弃而不是裁切 |
| `MENU_EDGE_PADDING` | `6.0` | 菜单夹取时与窗口边缘的间距 |
| `TOAST_SECS` / `TOAST_FADE_SECS` / `MAX_TOASTS` | `2.6` / `0.6` / `3` | Toast 停留、淡出与并发上限 |

样式（颜色、字号、圆角）另见 `pet-runtime/src/ui/theme.rs`；两者的分工是
`config.rs` 管**行为与几何**，`theme.rs` 管**观感**。改 UI 前请先读
[standards/RUNTIME_UX.md](standards/RUNTIME_UX.md)（含 ASCII-only 硬约束）。

---

## 配置文件（未来）

当前版本通过环境变量 + CLI 参数配置。未来将支持 JSON 配置文件：

```json
{
  "pet_name": "my-cat",
  "classifier": {
    "model": "qwen3.7-plus",
    "temperature": 0.1,
    "confidence_threshold": 0.7
  },
  "providers": {
    "image_provider": "azure",
    "video_provider": "kling"
  },
  "pipeline": {
    "frame_size": 256,
    "fps": 12,
    "output_dir": "./output"
  }
}
```

**已预留接口：**

```python
# 加载
settings = Settings.from_file(Path("pet-gen.config.json"))

# 保存
settings.save_to_file(Path("pet-gen.config.json"))
```

**优先级调整（未来）：**

```
CLI 参数  >  环境变量  >  配置文件  >  代码默认值
```

---

## UI 扩展预留

`Settings` 提供完整的序列化/反序列化接口，为未来 GUI 面板或 Web UI 预留扩展口：

### 序列化接口

```python
# Settings → dict（可 JSON 化）
config_dict = settings.to_dict()

# Settings → JSON 字符串
json_str = settings.to_json(indent=2)

# dict → Settings（忽略未知字段，兼容版本演进）
settings = Settings.from_dict(config_dict)

# JSON 字符串 → Settings
settings = Settings.from_json(json_str)
```

### 设计要点

| 特性 | 说明 |
|------|------|
| **忽略未知字段** | `from_dict()` 自动过滤不认识的 key，保证前后版本兼容 |
| **嵌套递归构造** | 嵌套 dataclass（Classifier/Provider/Pipeline）自动从 dict 递归构造 |
| **dataclass 驱动** | 基于 `dataclasses.asdict()` 序列化，新增字段自动包含 |
| **无副作用** | 序列化/反序列化不触发 API 调用或文件 I/O（`from_file`/`save_to_file` 除外） |

### UI 集成示例

```python
# 未来 UI 面板伪代码
class SettingsPanel:
    def load(self) -> dict:
        """UI 启动时加载当前配置为表单数据。"""
        return Settings.from_env().to_dict()

    def apply(self, form_data: dict) -> Settings:
        """用户提交表单后构建 Settings。"""
        return Settings.from_dict(form_data)

    def save_preset(self, settings: Settings, path: Path):
        """保存配置预设。"""
        settings.save_to_file(path)
```
