"""端到端管线回放 — Stage 0→7，零网络、零模型、零 ffmpeg。

「需要调接口的阶段」通过录制回放进入自动化测试：分类响应与图像产物都取自
`tests/fixtures/ai_pipeline/` 里的真实 AI 输出（见该目录 README 的来源说明），
provider 只做回放并记录调用，由测试断言编排行为。

覆盖的编排语义：
- 全链路贯通（skip_video 的 2 帧 fallback 路径，与录制素材的真实产生方式一致）
- 视频路径（Stage 3/4）的调度与产物缓存
- 断点续跑：二次运行命中缓存，零图像 API 调用
- 空帧动作的显式隔离（不污染下游）
- `body_type_override` 短路分类，不触碰 Vision provider
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pet_generator.config import Settings
from pet_generator.pipeline import Pipeline
from tests.support import fakes, rust_asserts, synth

pytestmark = pytest.mark.slow

STAGE_DIRS = (
    "00_classification",
    "01_standard",
    "02_poses",
    "03_videos",
    "04_frames",
    "05_nobg",
    "06_sprites",
)


@pytest.fixture
def replay(monkeypatch, ai_assets: Path):
    """把三个 provider 工厂与抠图器替换为回放实现，返回可断言的假实例集合。"""
    import pet_generator.providers as providers_mod
    import pet_generator.stages.bg_remover as bg_mod

    vision = fakes.ReplayVisionProvider(ai_assets / "classification.json")
    image = fakes.ReplayImageProvider(ai_assets)
    video = fakes.ReplayVideoProvider()

    monkeypatch.setattr(providers_mod, "create_vision_provider", lambda *a, **k: vision)
    monkeypatch.setattr(providers_mod, "create_image_provider", lambda *a, **k: image)
    monkeypatch.setattr(providers_mod, "create_video_provider", lambda *a, **k: video)
    monkeypatch.setattr(bg_mod, "BackgroundRemover", fakes.PassthroughBackgroundRemover)

    return {"vision": vision, "image": image, "video": video}


def _settings(tmp_path: Path, **overrides) -> Settings:
    settings = Settings(pet_name="ReplayPet")
    settings.pipeline.output_dir = str(tmp_path / "run")
    settings.pipeline.skip_video = True
    settings.pipeline.no_compile = True
    settings.pipeline.frame_size = 256
    settings.selected_actions = ["idle", "wave", "yawn"]
    for key, value in overrides.items():
        setattr(settings.pipeline, key, value)
    return settings


# ---------------------------------------------------------------------------
# 全链路
# ---------------------------------------------------------------------------


def test_pipeline_end_to_end_skip_video(replay, portraits: Path, tmp_path: Path):
    """Stage 0→7 全部跑通，各阶段产物落位，最终生成可编译的 Rust 项目。"""
    settings = _settings(tmp_path)
    project = Pipeline(settings).run(portraits / "figure_anime_a.png")

    base = Path(settings.pipeline.output_dir)
    for name in STAGE_DIRS:
        assert (base / name).is_dir(), f"缺少阶段目录 {name}"

    # Stage 0：分类结果落盘，且回放的真实响应被正确解析
    result = json.loads((base / "00_classification" / "result.json").read_text(encoding="utf-8"))
    assert result["body_type"] == "humanoid"
    assert result["style_target"] == "chibi_anime"
    assert len(replay["vision"].calls) == 1

    # Stage 2：每个选中动作一张尾帧，命名规范化为 <action>.png
    for action in settings.selected_actions:
        assert (base / "02_poses" / f"{action}.png").exists()
    # skip_video 模式不应触碰视频 provider
    assert replay["video"].calls == []

    # Stage 6：manifest 与 sheet 齐备
    manifest = json.loads((base / "06_sprites" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["frame_size"] == 256
    assert set(manifest["actions"]) == set(settings.selected_actions)
    for meta in manifest["actions"].values():
        # skip_video 用 [标准图, 尾帧] 两帧
        assert meta["frame_count"] == 2

    # Stage 7：项目结构与契约常量
    assert project == base / "ReplayPet"
    main_rs = project / "src" / "main.rs"
    rust_asserts.assert_project_structure(project)
    rust_asserts.assert_frame_size(main_rs, 256)
    rust_asserts.assert_no_legacy_atlas_markers(main_rs)
    entries = rust_asserts.sprite_sheet_entries(main_rs)
    assert {m["variant"] for m in entries} == {"Idle", "Wave", "Yawn"}


def test_pipeline_resume_hits_pose_cache(replay, portraits: Path, tmp_path: Path):
    """二次运行命中尾帧缓存：图像 API 只被标准化调用，动作尾帧零调用。"""
    settings = _settings(tmp_path)
    portrait = portraits / "figure_anime_a.png"
    Pipeline(settings).run(portrait)
    first_round_edits = [c for c in replay["image"].calls if c.kwargs.get("action")]
    assert len(first_round_edits) == len(settings.selected_actions)

    replay["image"].calls.clear()
    Pipeline(settings).run(portrait)
    second_round_edits = [c for c in replay["image"].calls if c.kwargs.get("action")]
    assert second_round_edits == [], "尾帧应全部命中缓存，不得再调图像 API"


def test_pipeline_video_path_uses_provider_and_extractor(
    replay, monkeypatch, portraits: Path, tmp_path: Path
):
    """非 skip_video 路径：视频 provider 被调用，抽帧产物进入下游。"""
    import pet_generator.stages.frame_extractor as fe_mod

    class FakeExtractor:
        """跳过 ffmpeg，直接合成帧序列（ffmpeg 行为由其自身用例覆盖）。"""

        def extract(self, video: Path, out_dir: Path, *, fps: int, max_frames: int) -> list[Path]:
            return synth.make_frames(out_dir, 4, size=(300, 240))

    monkeypatch.setattr(fe_mod, "FrameExtractor", FakeExtractor)

    settings = _settings(tmp_path, skip_video=False)
    Pipeline(settings).run(portraits / "figure_anime_a.png")

    assert len(replay["video"].calls) == len(settings.selected_actions)
    base = Path(settings.pipeline.output_dir)
    manifest = json.loads((base / "06_sprites" / "manifest.json").read_text(encoding="utf-8"))
    for meta in manifest["actions"].values():
        assert meta["frame_count"] == 4, "抽帧结果应完整进入打包阶段"


def test_pipeline_drops_actions_with_empty_frames(
    replay, monkeypatch, portraits: Path, tmp_path: Path
):
    """某动作抽帧为空时，该动作被移除且管线继续（不污染下游 manifest）。"""
    import pet_generator.stages.frame_extractor as fe_mod

    class FlakyExtractor:
        def extract(self, video: Path, out_dir: Path, *, fps: int, max_frames: int) -> list[Path]:
            if out_dir.name == "wave":
                return []
            return synth.make_frames(out_dir, 3)

    monkeypatch.setattr(fe_mod, "FrameExtractor", FlakyExtractor)

    settings = _settings(tmp_path, skip_video=False)
    Pipeline(settings).run(portraits / "figure_anime_a.png")

    manifest = json.loads(
        (Path(settings.pipeline.output_dir) / "06_sprites" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert "wave" not in manifest["actions"]
    assert set(manifest["actions"]) == {"idle", "yawn"}


def test_body_type_override_skips_vision_provider(replay, portraits: Path, tmp_path: Path):
    """显式指定体型时不应调用 Vision provider（省一次 API）。"""
    settings = _settings(tmp_path)
    settings.body_type_override = "quadruped"
    settings.selected_actions = ["idle"]
    Pipeline(settings).run(portraits / "figure_anime_b.png")

    assert replay["vision"].calls == []
    manifest = json.loads(
        (Path(settings.pipeline.output_dir) / "06_sprites" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["body_type"] == "quadruped"


def test_missing_input_image_fails_fast(replay, tmp_path: Path):
    """输入图不存在时立即失败，不产生任何阶段目录。"""
    settings = _settings(tmp_path)
    with pytest.raises(FileNotFoundError):
        Pipeline(settings).run(tmp_path / "nope.png")
    assert not Path(settings.pipeline.output_dir).exists()
