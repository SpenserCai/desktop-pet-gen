"""模型分发脚本 — 清单一致性、URL 构造、校验逻辑。

不触网、不下载：只验证「清单与代码期望一致」和「校验/续传判据正确」。
真实下载由 `scripts/fetch_models.py --check` 在本机/CI 手动验证。
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fetch_models.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("fetch_models", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # dataclass 解析延迟注解时会查 sys.modules，必须先注册再执行
    sys.modules["fetch_models"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fm():
    return _load_module()


def test_registry_covers_bg_model_choices(fm):
    """脚本清单必须覆盖 `--bg-model` 的所有取值，否则用户拉不到模型。"""
    from pet_generator.stages.bg_remover import _MODEL_SPECS

    assert {m.key for m in fm.MODELS} == set(_MODEL_SPECS)


def test_local_names_match_runtime_lookup(fm):
    """落盘文件名必须与 bg_remover 的查找名一致。"""
    from pet_generator.stages.bg_remover import _MODEL_SPECS

    for spec in fm.MODELS:
        assert spec.local_name == _MODEL_SPECS[spec.key]["filename"]


def test_sha256_and_size_look_sane(fm):
    for spec in fm.MODELS:
        assert len(spec.sha256) == 64 and all(c in "0123456789abcdef" for c in spec.sha256)
        assert spec.size > 10_000_000, "ONNX 权重不该小于 10 MB，清单可能填错"


def test_download_url_uses_modelscope_repo_api(fm, monkeypatch):
    monkeypatch.delenv("MODELSCOPE_ENDPOINT", raising=False)
    url = fm.download_url(fm.MODELS[0])
    assert url.startswith("https://www.modelscope.cn/api/v1/models/")
    assert "/repo?" in url
    assert "Revision=master" in url
    assert "FilePath=" in url


def test_endpoint_override(fm, monkeypatch):
    monkeypatch.setenv("MODELSCOPE_ENDPOINT", "https://mirror.invalid/")
    assert fm.download_url(fm.MODELS[0]).startswith("https://mirror.invalid/api/v1/models/")


def test_verify_detects_missing_size_and_hash(fm, tmp_path: Path, capsys):
    spec = fm.MODELS[0]
    target = tmp_path / spec.local_name

    assert fm.verify(spec, target) is False  # 缺失

    target.write_bytes(b"too short")
    assert fm.verify(spec, target) is False  # 大小不符

    # 构造一个大小正确但内容错误的文件（稀疏写入，避免真占 168 MB）
    with target.open("wb") as fh:
        fh.truncate(spec.size)
    assert fm.verify(spec, target) is False  # sha256 不符
    out = capsys.readouterr().out
    assert "校验失败" in out


def test_verify_accepts_matching_file(fm, tmp_path: Path):
    """用一个自洽的小清单验证「大小 + sha256 双匹配即通过」。"""
    payload = b"fake onnx payload"
    target = tmp_path / "tiny.onnx"
    target.write_bytes(payload)
    spec = fm.ModelSpec(
        key="tiny",
        local_name="tiny.onnx",
        repo="org/repo",
        revision="master",
        remote_path="tiny.onnx",
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        note="test",
    )
    assert fm.verify(spec, target) is True


def test_check_mode_reports_missing_without_network(fm, tmp_path: Path):
    """--check 在模型缺失时返回 1，且不发起任何网络请求。"""
    import urllib.request

    def _boom(*args, **kwargs):  # pragma: no cover - 一旦被调用即测试失败
        raise AssertionError("--check 不应发起网络请求")

    original = urllib.request.urlopen
    urllib.request.urlopen = _boom
    try:
        assert fm.main(["--check", "--dest", str(tmp_path)]) == 1
    finally:
        urllib.request.urlopen = original


def test_list_mode_exits_zero(fm, capsys):
    assert fm.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "AI-ModelScope/u2net" in out
    assert "AI-ModelScope/RMBG-2.0" in out
