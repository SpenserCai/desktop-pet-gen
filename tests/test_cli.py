"""CLI — 参数解析与 Settings 映射（优先级：CLI > 环境变量 > 默认值）。

不执行管线，只验证「命令行怎么写 → 配置变成什么」这条映射，
因为它是用户唯一的入口，错一个字段就整条管线跑偏。
"""

from __future__ import annotations

import pytest

from pet_generator.cli import build_parser, build_settings

ENV_KEYS = (
    "PET_NAME",
    "PET_IMAGE_PROVIDER",
    "PET_VIDEO_PROVIDER",
    "PET_FRAME_SIZE",
    "PET_OUTPUT_DIR",
    "PET_BODY_TYPE",
    "PET_SKIP_VIDEO",
    "PET_NO_COMPILE",
    "PET_DEBUG_BUILD",
    "PET_VERBOSE",
    "PET_BG_MODEL",
    "CLASSIFIER_MODEL",
    "CLASSIFIER_API_BASE",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """隔离环境变量，避免宿主环境干扰 CLI 映射断言。"""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _settings(argv: list[str]):
    return build_settings(build_parser().parse_args(argv))


def test_minimal_invocation_uses_defaults():
    settings = _settings(["--image", "cat.png"])
    assert settings.pipeline.skip_video is False
    assert settings.pipeline.no_compile is False
    assert settings.pipeline.debug_build is False
    assert settings.pipeline.verbose is False
    assert settings.body_type_override is None


def test_scalar_options_map_to_settings():
    settings = _settings(
        [
            "--image",
            "cat.png",
            "--name",
            "Mimi",
            "--output-dir",
            "/tmp/pets",
            "--frame-size",
            "512",
            "--bg-model",
            "rmbg",
            "--body-type",
            "quadruped",
            "--image-provider",
            "bailian",
            "--video-provider",
            "wan27",
            "--classifier-model",
            "qwen-vl-max",
            "--classifier-base",
            "https://example.invalid/v1",
        ]
    )
    assert settings.pet_name == "Mimi"
    assert settings.pipeline.output_dir == "/tmp/pets"
    assert settings.pipeline.frame_size == 512
    assert settings.pipeline.bg_model == "rmbg"
    assert settings.body_type_override == "quadruped"
    assert settings.providers.image_provider == "bailian"
    assert settings.providers.video_provider == "wan27"
    assert settings.classifier.model == "qwen-vl-max"
    assert settings.classifier.api_base == "https://example.invalid/v1"


def test_boolean_flags_map_to_settings():
    settings = _settings(
        ["--image", "cat.png", "--skip-video", "--no-compile", "--debug", "--verbose"]
    )
    assert settings.pipeline.skip_video is True
    assert settings.pipeline.no_compile is True
    assert settings.pipeline.debug_build is True
    assert settings.pipeline.verbose is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("idle,wave", ["idle", "wave"]),
        (" idle , wave ", ["idle", "wave"]),
        ("idle,,wave,", ["idle", "wave"]),
        ("idle", ["idle"]),
    ],
)
def test_actions_are_split_and_trimmed(raw: str, expected: list[str]):
    settings = _settings(["--image", "cat.png", "--actions", raw])
    assert settings.selected_actions == expected


def test_cli_overrides_environment(monkeypatch):
    monkeypatch.setenv("PET_NAME", "FromEnv")
    monkeypatch.setenv("PET_FRAME_SIZE", "128")
    settings = _settings(["--image", "cat.png", "--name", "FromCli"])
    assert settings.pet_name == "FromCli", "CLI 必须覆盖环境变量"
    assert settings.pipeline.frame_size == 128, "未在 CLI 指定的项应保留环境变量值"


def test_environment_only_is_respected(monkeypatch):
    monkeypatch.setenv("PET_OUTPUT_DIR", "/tmp/env-out")
    monkeypatch.setenv("PET_SKIP_VIDEO", "true")
    settings = _settings(["--image", "cat.png"])
    assert settings.pipeline.output_dir == "/tmp/env-out"
    assert settings.pipeline.skip_video is True


def test_image_argument_is_required():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
