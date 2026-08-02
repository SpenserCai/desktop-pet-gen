"""配置模块 — 聚合配置中心与领域配置。

导出:
    Settings: 聚合配置中心（单一事实源）
    ClassifierSettings: 分类器连接参数
    ProviderSettings: Provider 选择与凭据
    PipelineSettings: 管线运行参数
    ClassifierConfig: 分类器领域配置（提示词、分类规则）
"""

from pet_generator.config.classifier_config import (
    VALID_BODY_TYPES,
    VALID_INPUT_MATERIALS,
    VALID_STYLE_TARGETS,
    ClassifierConfig,
)
from pet_generator.config.settings import (
    ClassifierSettings,
    PipelineSettings,
    ProviderSettings,
    Settings,
)

__all__ = [
    "VALID_BODY_TYPES",
    "VALID_INPUT_MATERIALS",
    "VALID_STYLE_TARGETS",
    "ClassifierConfig",
    "ClassifierSettings",
    "PipelineSettings",
    "ProviderSettings",
    "Settings",
]
