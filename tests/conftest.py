"""pytest 共享夹具。

`pet_generator` 的可导入性由 `pyproject.toml` 的 `pythonpath = ["."]` 保证，
测试文件里不需要任何 `sys.path` 操作。

约定：
- 夹具目录只读；需要改动的素材先复制到 `tmp_path`。
- 任何产物都写 `tmp_path`，测试结束由 pytest 回收，仓库内不留垃圾。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
FIXTURES = TESTS_DIR / "fixtures"


@pytest.fixture(scope="session")
def project_root() -> Path:
    """`desktop-pet-gen` 目录（模板、模型、pyproject 的所在）。"""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def template_dir(project_root: Path) -> Path:
    """Rust 运行时模板目录。"""
    return project_root / "pet-runtime"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """夹具根目录（只读）。"""
    return FIXTURES


@pytest.fixture(scope="session")
def portraits() -> Path:
    """输入原图目录（只读）。"""
    return FIXTURES / "portraits"


@pytest.fixture(scope="session")
def ai_assets() -> Path:
    """真实 AI 产物录制目录（只读）。见 fixtures/README.md。"""
    path = FIXTURES / "ai_pipeline"
    if not path.exists():  # pragma: no cover - 夹具缺失属于环境错误
        pytest.skip(f"缺少 AI 录制夹具: {path}")
    return path


@pytest.fixture(scope="session")
def recorded_classification(ai_assets: Path) -> dict:
    """录制的真实分类结果（`ClassificationResult.to_dict()` 形态）。"""
    return json.loads((ai_assets / "classification.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def humanoid_actions() -> list[str]:
    """录制素材覆盖的动作名（与 humanoid 动作集一致）。"""
    return sorted(p.stem for p in (FIXTURES / "ai_pipeline" / "poses").glob("*.png"))
