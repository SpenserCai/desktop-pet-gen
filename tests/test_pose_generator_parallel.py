"""PoseGenerator 并发化 — 离线单元测试。

不触网、不依赖 Azure 凭据：用 FakeImageProvider 模拟 I/O（短 sleep），
验证并发逻辑、返回语义、失败隔离、临时文件撞名回归与空列表健壮性。

运行: pytest tests/test_pose_generator_parallel.py -v
"""

from __future__ import annotations

import time
from pathlib import Path

from pet_generator.config.actions.base import ActionDef
from pet_generator.providers.base import GenerationResult, ImageGenProvider
from pet_generator.stages.pose_generator import PoseGenerator


def _make_actions(names: list[str]) -> list[ActionDef]:
    """构造一批最简 ActionDef（仅测试所需字段有意义）。"""
    return [
        ActionDef(
            name=n,
            description=f"desc-{n}",
            pose_prompt=f"pose of {n}",
            video_prompt=f"video of {n}",
            duration_secs=3.0,
        )
        for n in names
    ]


class FakeImageProvider(ImageGenProvider):
    """可控成功/失败、带短 sleep 模拟 I/O 的假 Provider。

    - 每次 edit() 在 output_dir 内写入一个临时 png 并返回其路径。
    - ``fail_names``: prompt 中包含这些动作名时返回 success=False（模拟失败）。
    - ``fixed_tmp_name``: 若为 True，临时文件用【固定】文件名（模拟 Azure
      秒级时间戳撞名），用于回归验证“每动作独立临时子目录”的隔离效果。
    - ``sleep_secs``: 模拟 I/O 阻塞时长，制造并发重叠窗口。
    """

    def __init__(
        self,
        fail_names: set[str] | None = None,
        fixed_tmp_name: bool = False,
        sleep_secs: float = 0.2,
    ) -> None:
        self.fail_names = fail_names or set()
        self.fixed_tmp_name = fixed_tmp_name
        self.sleep_secs = sleep_secs
        self.edit_calls: list[Path] = []  # 记录每次 edit 收到的 output_dir

    def generate(self, prompt, output_dir, *, size="1024x1024", quality="medium", n=1):
        # 本测试只用 edit()，generate 不会被调用
        return GenerationResult(success=False, error="not used")

    def edit(self, image_paths, prompt, output_dir, *, size="1024x1024", quality="medium"):
        time.sleep(self.sleep_secs)  # 模拟 I/O，制造并发重叠
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self.edit_calls.append(output_dir)

        # 按 prompt 决定成功/失败
        if any(name in prompt for name in self.fail_names):
            return GenerationResult(success=False, error="simulated failure")

        # 成功 → 落盘一个临时 png（内容为 prompt，便于校验“错图/串图”）
        if self.fixed_tmp_name:
            # 固定文件名 → 若无每动作子目录隔离，必然撞名覆盖
            tmp = output_dir / "20260801_190000_edited_0.png"
        else:
            # 唯一文件名（用纳秒，模拟正常但可能重叠的场景）
            tmp = output_dir / f"{time.time_ns()}_edited_0.png"
        tmp.write_text(prompt, encoding="utf-8")
        return GenerationResult(success=True, output_paths=[tmp])


# --------------------------------------------------------------------------- #
# 测试用例
# --------------------------------------------------------------------------- #


def test_all_success_concurrent_faster_than_serial(tmp_path):
    """(a) 10 动作全成功：返回 10 项、文件名为 {name}.png、并发显著快于串行。"""
    names = [f"action_{i}" for i in range(10)]
    actions = _make_actions(names)
    provider = FakeImageProvider(sleep_secs=0.2)
    gen = PoseGenerator(provider, max_workers=5)

    standard = tmp_path / "standard.png"
    standard.write_text("std", encoding="utf-8")
    out_dir = tmp_path / "02_poses"

    start = time.monotonic()
    result = gen.run(standard, actions, "humanoid", out_dir)
    elapsed = time.monotonic() - start

    # 10 项全成功
    assert len(result) == 10, f"expected 10, got {len(result)}"
    assert set(result.keys()) == set(names)

    # 文件名 == {name}.png 且确实存在
    for name in names:
        p = result[name]
        assert p.name == f"{name}.png", f"bad filename {p.name}"
        assert p.parent == out_dir
        assert p.exists(), f"missing {p}"
        # 内容正确（无串图）：落盘内容应含本动作 prompt
        assert name in p.read_text(encoding="utf-8"), f"wrong content for {name}"

    # 并发耗时显著小于串行（串行 ≈ 10*0.2=2.0s；并发 5 worker ≈ 2 波次 ≈ 0.4s）
    serial_estimate = 10 * 0.2
    assert elapsed < serial_estimate * 0.6, (
        f"concurrent {elapsed:.2f}s not significantly faster than serial ~{serial_estimate:.2f}s"
    )


def test_partial_failure_warn_skip_no_raise(tmp_path):
    """(b) 部分失败：仅 warn+skip 不抛异常，返回项不含失败项。"""
    names = [f"action_{i}" for i in range(10)]
    fail = {"action_3", "action_7"}
    actions = _make_actions(names)
    provider = FakeImageProvider(fail_names=fail, sleep_secs=0.05)
    gen = PoseGenerator(provider, max_workers=3)

    standard = tmp_path / "standard.png"
    standard.write_text("std", encoding="utf-8")
    out_dir = tmp_path / "02_poses"

    # 不应抛异常
    result = gen.run(standard, actions, "humanoid", out_dir)

    expected_ok = set(names) - fail
    assert set(result.keys()) == expected_ok, f"expected {expected_ok}, got {set(result.keys())}"
    assert len(result) == 8
    # 失败项不应有产物文件
    for name in fail:
        assert not (out_dir / f"{name}.png").exists(), f"{name} should be absent"


def test_collision_regression_fixed_tmp_name(tmp_path):
    """(c) 撞名回归：fake provider 用固定临时文件名，验证每动作临时子目录后
    仍产出 10 个正确、互不覆盖的 {name}.png。"""
    names = [f"action_{i}" for i in range(10)]
    actions = _make_actions(names)
    # 固定临时文件名 + 极短 sleep → 最大化撞名窗口
    provider = FakeImageProvider(fixed_tmp_name=True, sleep_secs=0.02)
    gen = PoseGenerator(provider, max_workers=5)

    standard = tmp_path / "standard.png"
    standard.write_text("std", encoding="utf-8")
    out_dir = tmp_path / "02_poses"

    result = gen.run(standard, actions, "humanoid", out_dir)

    # 10 项全成功且互不覆盖
    assert len(result) == 10, f"expected 10, got {len(result)}"
    for name in names:
        p = out_dir / f"{name}.png"
        assert p.exists(), f"missing {p}"
        # 关键：内容必须对应该动作（无错图/串图）
        content = p.read_text(encoding="utf-8")
        assert name in content, f"collision! {name}.png has wrong content: {content!r}"

    # 额外守护：每次 edit 收到的 output_dir 应为各自独立的 .tmp_{name} 子目录
    tmp_dirs = set(provider.edit_calls)
    assert len(tmp_dirs) == 10, f"expected 10 distinct tmp dirs, got {len(tmp_dirs)}: {tmp_dirs}"
    for d in tmp_dirs:
        assert d.parent == out_dir
        assert d.name.startswith(".tmp_"), f"unexpected tmp dir {d.name}"


def test_empty_actions_returns_empty(tmp_path):
    """(d) 空列表：返回 {} 且不抛异常。"""
    provider = FakeImageProvider()
    gen = PoseGenerator(provider, max_workers=3)
    standard = tmp_path / "standard.png"
    standard.write_text("std", encoding="utf-8")
    out_dir = tmp_path / "02_poses"

    result = gen.run(standard, [], "humanoid", out_dir)
    assert result == {}
    # 空列表不应触发任何 edit 调用
    assert provider.edit_calls == []


def test_max_workers_one_degenerates_to_serial(tmp_path):
    """(补充) max_workers=1 退化串行：结果集与并发一致。"""
    names = [f"action_{i}" for i in range(5)]
    actions = _make_actions(names)
    provider = FakeImageProvider(sleep_secs=0.01)
    gen = PoseGenerator(provider, max_workers=1)

    standard = tmp_path / "standard.png"
    standard.write_text("std", encoding="utf-8")
    out_dir = tmp_path / "02_poses"

    result = gen.run(standard, actions, "humanoid", out_dir)
    assert set(result.keys()) == set(names)
    assert len(result) == 5
