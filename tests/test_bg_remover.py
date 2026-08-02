"""Stage 5 去背景 — 模型查找链、EP 选择、降级行为。

全程 mock：不加载 658 MB ONNX 权重，也不要求安装 onnxruntime 的任何 EP。
真实推理质量由「素材过管线」与人工验收覆盖，这里只锁住**查找与选择逻辑**，
因为它是跨平台部署时最容易悄悄退化的一环。
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from PIL import Image

from pet_generator.stages import bg_remover as bg

# ---------------------------------------------------------------------------
# 模型查找链：显式路径 → 环境变量 → 项目 models/ → 用户主目录
# ---------------------------------------------------------------------------


def test_explicit_path_wins_and_does_not_fall_back(tmp_path: Path, monkeypatch):
    """显式路径存在则采用；不存在则返回 None（绝不静默回退到其他候选）。"""
    model = tmp_path / "custom.onnx"
    model.write_bytes(b"fake")
    assert bg._find_model_path("u2net", model) == model

    missing = tmp_path / "nope.onnx"
    monkeypatch.setenv("U2NET_MODEL_PATH", str(model))  # 即便环境变量可用也不回退
    assert bg._find_model_path("u2net", missing) is None


def test_env_var_takes_precedence_over_project_dir(tmp_path: Path, monkeypatch):
    """环境变量优先于项目 models/ 目录。"""
    env_model = tmp_path / "env-u2net.onnx"
    env_model.write_bytes(b"fake")
    monkeypatch.setenv("U2NET_MODEL_PATH", str(env_model))
    assert bg._find_model_path("u2net") == env_model


def test_project_models_dir_is_searched(monkeypatch, project_root: Path):
    """未设环境变量时应命中项目自带的 models/<filename>（随目录分发的前提）。"""
    monkeypatch.delenv("U2NET_MODEL_PATH", raising=False)
    expected = project_root / "models" / "u2net.onnx"
    found = bg._find_model_path("u2net")
    if expected.is_file():
        assert found == expected
    else:  # 干净克隆（模型未下载）应返回 None 而不是抛异常
        assert found is None or found != expected


def test_missing_everywhere_returns_none(monkeypatch, tmp_path: Path):
    """全部候选都不存在时返回 None，由调用方决定降级。"""
    monkeypatch.delenv("RMBG_MODEL_PATH", raising=False)
    monkeypatch.setattr(bg.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(
        bg, "_MODEL_SPECS", {**bg._MODEL_SPECS, "rmbg": {**bg._MODEL_SPECS["rmbg"]}}
    )
    # 把项目候选指向空目录：改 __file__ 不现实，改用不存在的文件名
    bg._MODEL_SPECS["rmbg"]["filename"] = "definitely-absent.onnx"
    assert bg._find_model_path("rmbg") is None


# ---------------------------------------------------------------------------
# EP 选择：与 onnxruntime 实际可用集取交集，且 CPU 必须兜底
# ---------------------------------------------------------------------------


def _fake_ort(available: list[str]) -> types.ModuleType:
    module = types.ModuleType("onnxruntime")
    module.get_available_providers = lambda: available  # type: ignore[attr-defined]
    return module


@pytest.mark.parametrize(
    ("available", "expected"),
    [
        (
            ["CUDAExecutionProvider", "CPUExecutionProvider"],
            ["CUDAExecutionProvider", "CPUExecutionProvider"],
        ),
        (
            ["CoreMLExecutionProvider", "CPUExecutionProvider"],
            ["CoreMLExecutionProvider", "CPUExecutionProvider"],
        ),
        (["CPUExecutionProvider"], ["CPUExecutionProvider"]),
        # 未知 EP 不应被请求
        (["TensorrtExecutionProvider", "CPUExecutionProvider"], ["CPUExecutionProvider"]),
    ],
)
def test_provider_priority_intersects_with_available(monkeypatch, available, expected):
    monkeypatch.setitem(sys.modules, "onnxruntime", _fake_ort(available))
    assert bg._build_providers() == expected


def test_provider_list_always_ends_with_cpu(monkeypatch):
    """即使 onnxruntime 未报告 CPU EP，也必须保留 CPU 兜底。"""
    monkeypatch.setitem(sys.modules, "onnxruntime", _fake_ort([]))
    assert bg._build_providers()[-1] == "CPUExecutionProvider"


# ---------------------------------------------------------------------------
# 构造与降级
# ---------------------------------------------------------------------------


def test_invalid_model_type_raises():
    with pytest.raises(ValueError, match="model_type"):
        bg.BackgroundRemover(model_type="not-a-model")


def test_unavailable_model_degrades_to_copy(tmp_path: Path, monkeypatch):
    """模型不可用时不得崩溃：帧被原样输出，管线继续。"""
    monkeypatch.setattr(bg, "_find_model_path", lambda *a, **k: None)
    remover = bg.BackgroundRemover(model_type="u2net")
    assert remover.is_available is False

    src = tmp_path / "src"
    src.mkdir()
    frame = src / "frame_0000.png"
    Image.new("RGB", (32, 32), (10, 20, 30)).save(frame, format="PNG")

    out = remover.remove_batch([frame], tmp_path / "out")
    assert len(out) == 1
    assert out[0].exists()


def test_session_creation_failure_degrades(tmp_path: Path, monkeypatch):
    """ONNX 会话创建失败（如 EP 不兼容）时降级而非抛异常。"""
    model = tmp_path / "u2net.onnx"
    model.write_bytes(b"not a real model")
    monkeypatch.setattr(bg, "_find_model_path", lambda *a, **k: model)

    module = _fake_ort(["CPUExecutionProvider"])

    def _boom(*args, **kwargs):
        raise RuntimeError("invalid protobuf")

    module.InferenceSession = _boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "onnxruntime", module)

    remover = bg.BackgroundRemover(model_type="u2net")
    assert remover.is_available is False
