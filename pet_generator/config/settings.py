"""聚合配置中心 — 单一事实源 (Single Source of Truth)。

设计原则:
- 所有配置集中管理，各子模块通过 Settings 实例获取配置
- 优先级: CLI args > 环境变量 > 配置文件(未来) > 默认值
- 序列化友好: to_dict() / from_dict() 支持未来 UI 面板读写
- 模块化: 按职责拆分为 ClassifierSettings / ProviderSettings / PipelineSettings

Usage:
    from pet_generator.config import Settings

    settings = Settings.from_env()
    settings.pipeline.frame_size = 512  # CLI override
    print(settings.classifier.model)
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


@dataclass
class ClassifierSettings:
    """视觉分类器配置 — 用于宠物体型/类型识别。"""

    model: str = "qwen3.7-plus"
    api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key_env: str = "DASHSCOPE_API_KEY"
    temperature: float = 0.1
    max_tokens: int = 1024
    max_retries: int = 2
    confidence_threshold: float = 0.7
    timeout: int = 60  # 单次请求超时（秒）

    @property
    def api_key(self) -> str:
        """从环境变量解析 API Key。"""
        return os.environ.get(self.api_key_env, "")


@dataclass
class ProviderSettings:
    """生成 Provider 选择配置。"""

    image_provider: str = "azure"  # "azure" | "bailian"
    video_provider: str = "kling"  # "kling" | "wan27"

    # Azure GPT-Image-2
    azure_api_key_env: str = "AZURE_OPENAI_API_KEY"
    azure_endpoint_env: str = "AZURE_OPENAI_ENDPOINT"
    azure_api_version: str = "2025-04-01-preview"
    azure_model: str = "gpt-image-2"

    # 百炼 DashScope (图像 + 视频共用)
    dashscope_api_key_env: str = "DASHSCOPE_API_KEY"
    dashscope_base_url: str = "https://dashscope.aliyuncs.com"

    # Kling 视频
    kling_model: str = "kling/kling-v3-omni-video-generation"

    # WAN 2.7 视频
    wan_i2v_model: str = "wan2.7-i2v"
    wan_t2v_model: str = "wan2.7-t2v"

    # WAN 2.7 图像
    wan_image_model: str = "wan2.7-image-pro"

    @property
    def azure_api_key(self) -> str:
        return os.environ.get(self.azure_api_key_env, "")

    @property
    def azure_endpoint(self) -> str:
        return os.environ.get(self.azure_endpoint_env, "")

    @property
    def dashscope_api_key(self) -> str:
        return os.environ.get(self.dashscope_api_key_env, "")


@dataclass
class PipelineSettings:
    """管线运行参数配置。"""

    frame_size: int = 256  # 精灵图帧尺寸（正方形）
    output_dir: str = "./output"
    skip_video: bool = False  # 跳过视频生成（调试用）
    no_compile: bool = False  # 跳过 Rust 编译
    debug_build: bool = False  # Rust debug 模式编译
    verbose: bool = False  # 详细日志
    fps: int = 12  # 默认帧率
    poll_interval: int = 10  # 异步任务轮询间隔（秒）
    task_timeout: int = 600  # 异步任务超时（秒）
    bg_model: str = "u2net"  # 去背景模型: "u2net"(快速) | "rmbg"(RMBG-2.0, 高质量)

    @property
    def output_path(self) -> Path:
        """输出目录的 Path 对象。"""
        return Path(self.output_dir)


@dataclass
class Settings:
    """聚合配置中心 — 单一事实源。

    优先级: CLI args > 环境变量 > 配置文件(未来) > 默认值
    未来 UI 可通过 to_dict()/from_dict() 序列化。

    Attributes:
        pet_name: 宠物项目名称（用于输出目录与 manifest）
        classifier: 视觉分类器配置
        providers: 生成 Provider 选择与凭据配置
        pipeline: 管线运行参数
        body_type_override: 手动指定体型（跳过 AI 分类），如 "quadruped"
        selected_actions: 手动选择要生成的动作子集，None 表示全部
    """

    pet_name: str = "my-pet"
    classifier: ClassifierSettings = field(default_factory=ClassifierSettings)
    providers: ProviderSettings = field(default_factory=ProviderSettings)
    pipeline: PipelineSettings = field(default_factory=PipelineSettings)
    body_type_override: str | None = None
    selected_actions: list[str] | None = None

    # ─── 序列化 ───────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """序列化为可 JSON 化的字典（支持 UI 面板 / 配置文件持久化）。"""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """序列化为 JSON 字符串。"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> Settings:
        """从字典反序列化（忽略未知字段，兼容版本演进）。"""
        known_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known_fields}

        # 嵌套 dataclass 递归构造
        if "classifier" in filtered and isinstance(filtered["classifier"], dict):
            cls_fields = {f.name for f in fields(ClassifierSettings)}
            filtered["classifier"] = ClassifierSettings(
                **{k: v for k, v in filtered["classifier"].items() if k in cls_fields}
            )
        if "providers" in filtered and isinstance(filtered["providers"], dict):
            cls_fields = {f.name for f in fields(ProviderSettings)}
            filtered["providers"] = ProviderSettings(
                **{k: v for k, v in filtered["providers"].items() if k in cls_fields}
            )
        if "pipeline" in filtered and isinstance(filtered["pipeline"], dict):
            cls_fields = {f.name for f in fields(PipelineSettings)}
            filtered["pipeline"] = PipelineSettings(
                **{k: v for k, v in filtered["pipeline"].items() if k in cls_fields}
            )

        return cls(**filtered)

    @classmethod
    def from_json(cls, json_str: str) -> Settings:
        """从 JSON 字符串反序列化。"""
        return cls.from_dict(json.loads(json_str))

    # ─── 环境变量加载 ─────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> Settings:
        """从环境变量加载配置（覆盖默认值）。

        支持的环境变量:
            PET_NAME: 宠物名称
            PET_IMAGE_PROVIDER: 图像 Provider (azure|bailian)
            PET_VIDEO_PROVIDER: 视频 Provider (kling|wan27)
            PET_FRAME_SIZE: 帧尺寸
            PET_OUTPUT_DIR: 输出目录
            PET_BODY_TYPE: 体型覆盖
            PET_SKIP_VIDEO: 跳过视频 (1/true)
            PET_NO_COMPILE: 跳过编译 (1/true)
            PET_DEBUG_BUILD: Debug 编译 (1/true)
            PET_VERBOSE: 详细日志 (1/true)
            PET_FPS: 帧率
            PET_BG_MODEL: 去背景模型 (u2net|rmbg)
            CLASSIFIER_MODEL: 分类器模型
            CLASSIFIER_API_BASE: 分类器 API 地址
            CLASSIFIER_API_KEY_ENV: 分类器 API Key 环境变量名
        """
        settings = cls()

        # 顶层
        if v := os.environ.get("PET_NAME"):
            settings.pet_name = v
        if v := os.environ.get("PET_BODY_TYPE"):
            settings.body_type_override = v

        # Provider 选择
        if v := os.environ.get("PET_IMAGE_PROVIDER"):
            settings.providers.image_provider = v
        if v := os.environ.get("PET_VIDEO_PROVIDER"):
            settings.providers.video_provider = v

        # Pipeline
        if v := os.environ.get("PET_FRAME_SIZE"):
            settings.pipeline.frame_size = int(v)
        if v := os.environ.get("PET_OUTPUT_DIR"):
            settings.pipeline.output_dir = v
        if v := os.environ.get("PET_FPS"):
            settings.pipeline.fps = int(v)
        if _env_bool("PET_SKIP_VIDEO"):
            settings.pipeline.skip_video = True
        if _env_bool("PET_NO_COMPILE"):
            settings.pipeline.no_compile = True
        if _env_bool("PET_DEBUG_BUILD"):
            settings.pipeline.debug_build = True
        if _env_bool("PET_VERBOSE"):
            settings.pipeline.verbose = True
        if v := os.environ.get("PET_BG_MODEL"):
            settings.pipeline.bg_model = v

        # Classifier
        if v := os.environ.get("CLASSIFIER_MODEL"):
            settings.classifier.model = v
        if v := os.environ.get("CLASSIFIER_API_BASE"):
            settings.classifier.api_base = v
        if v := os.environ.get("CLASSIFIER_API_KEY_ENV"):
            settings.classifier.api_key_env = v

        return settings

    # ─── 配置文件加载（未来扩展）─────────────────────────────────────────

    @classmethod
    def from_file(cls, path: Path) -> Settings:
        """从 JSON 配置文件加载。文件不存在时返回默认配置。"""
        if not path.exists():
            return cls()
        return cls.from_json(path.read_text(encoding="utf-8"))

    def save_to_file(self, path: Path) -> None:
        """持久化当前配置到 JSON 文件。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")


def _env_bool(key: str) -> bool:
    """解析布尔型环境变量。"""
    val = os.environ.get(key, "").lower()
    return val in ("1", "true", "yes", "on")
