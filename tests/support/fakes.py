"""录制回放的假实现 — 让「需要调接口的阶段」进入自动化测试。

设计原则：**假实现只负责回放，不负责判断**。
每个假 provider 都记录收到的调用（`calls`），由测试断言调用次数/提示词/参数，
返回值则来自 `tests/fixtures/ai_pipeline/` 里录制的真实 AI 产物。
这样既零网络零成本，又保证下游拿到的是真实素材而非人造图。

覆盖的接口：
- `ReplayVisionProvider`    → Stage 0 分类（回放真实 JSON 响应）
- `ReplayImageProvider`     → Stage 1 标准化 / Stage 2 尾帧（回放真实 PNG）
- `ReplayVideoProvider`     → Stage 3 视频（合成最小 mp4，录制里没有视频产物）
- `PassthroughBackgroundRemover` → Stage 5 抠图（避免加载 658 MB ONNX 模型）
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from pet_generator.providers.base import (
    GenerationResult,
    ImageGenProvider,
    VideoGenProvider,
    VisionProvider,
)


@dataclass
class Call:
    """一次被记录的调用。"""

    method: str
    prompt: str = ""
    kwargs: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Stage 0：Vision
# ---------------------------------------------------------------------------


class ReplayVisionProvider(VisionProvider):
    """回放录制的分类响应。

    Args:
        recorded: `classification.json` 路径。
        raw_override: 直接指定 `classify()` 的返回字典（用于容错/异常路径测试）。
        fail_times: 前 N 次调用抛异常，用于验证重试与降级。
    """

    def __init__(
        self,
        recorded: Path | None = None,
        *,
        raw_override: dict | None = None,
        fail_times: int = 0,
    ) -> None:
        self._recorded = recorded
        self._raw_override = raw_override
        self._fail_times = fail_times
        self.calls: list[Call] = []

    def describe(self, image_path: Path, prompt: str = "Describe this image in detail.") -> str:
        self.calls.append(Call("describe", prompt))
        return "a chibi anime figure"

    def classify(self, image_path: Path, system_prompt: str, user_prompt: str) -> dict:
        self.calls.append(Call("classify", user_prompt, {"image": str(image_path)}))
        if len(self.calls) <= self._fail_times:
            raise RuntimeError("simulated vision failure")
        if self._raw_override is not None:
            return self._raw_override
        assert self._recorded is not None, "需要 recorded 或 raw_override 之一"
        data = json.loads(self._recorded.read_text(encoding="utf-8"))
        # 录制文件是 ClassificationResult.to_dict() 的形态；provider 契约要求返回
        # LLM 原始字典，所以优先回放 raw_response 原文。
        raw = data.get("raw_response")
        return json.loads(raw) if raw else data


# ---------------------------------------------------------------------------
# Stage 1 / 2：图像生成
# ---------------------------------------------------------------------------


class ReplayImageProvider(ImageGenProvider):
    """回放录制的图像产物。

    路由规则（不依赖提示词文本，因此不会被 prompt 改写破坏）：
    1. `PoseGenerator` 会把输出目录设为 ``<poses>/.tmp_<action>``，
       据此取 `poses/<action>.png`；
    2. 其余情况（`Standardizer` 直接传阶段目录）视为标准化，返回 `standard.png`；
    3. 兜底再按提示词里出现的动作名匹配一次。
    """

    def __init__(self, ai_assets: Path, *, fail_actions: set[str] | None = None) -> None:
        self._assets = ai_assets
        self._known_actions = sorted(p.stem for p in (ai_assets / "poses").glob("*.png"))
        self._fail_actions = fail_actions or set()
        self.calls: list[Call] = []

    # -- 内部 -------------------------------------------------------------
    def _emit(self, source: Path, output_dir: Path, stem: str) -> GenerationResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"{stem}.png"
        shutil.copy(source, target)
        return GenerationResult(success=True, output_paths=[target], metadata={"replayed": True})

    def _match_action(self, output_dir: Path, prompt: str) -> str | None:
        if output_dir.name.startswith(".tmp_"):
            candidate = output_dir.name[len(".tmp_") :]
            if candidate in self._known_actions:
                return candidate
        lowered = prompt.lower()
        # 长名优先（look_around 要先于 look 匹配）
        for name in sorted(self._known_actions, key=len, reverse=True):
            if name in lowered or name.replace("_", " ") in lowered:
                return name
        return None

    # -- 接口 -------------------------------------------------------------
    def generate(
        self,
        prompt: str,
        output_dir: Path,
        *,
        size: str = "1024x1024",
        quality: str = "medium",
        n: int = 1,
    ) -> GenerationResult:
        self.calls.append(Call("generate", prompt, {"size": size, "quality": quality, "n": n}))
        return self._emit(self._assets / "standard.png", output_dir, "generated_0")

    def edit(
        self,
        image_paths: list[Path],
        prompt: str,
        output_dir: Path,
        *,
        size: str = "1024x1024",
        quality: str = "medium",
    ) -> GenerationResult:
        action = self._match_action(output_dir, prompt)
        self.calls.append(
            Call("edit", prompt, {"inputs": len(image_paths), "size": size, "action": action})
        )
        if action is None:
            return self._emit(self._assets / "standard.png", output_dir, "edited_0")
        if action in self._fail_actions:
            return GenerationResult(success=False, error=f"simulated failure for {action}")
        return self._emit(
            self._assets / "poses" / f"{action}.png", output_dir, f"{action}_edited_0"
        )


# ---------------------------------------------------------------------------
# Stage 3：视频生成
# ---------------------------------------------------------------------------


class ReplayVideoProvider(VideoGenProvider):
    """产出最小可用视频文件。

    录制素材里没有视频（那次运行走的是 `skip_video`），所以这里写占位字节。
    只用于验证编排/缓存判据（Stage 3 的缓存阈值是「存在且 >100 KB」），
    真正的抽帧由 `FrameExtractor` 的独立用例覆盖。
    """

    def __init__(self, *, payload_kb: int = 128) -> None:
        self._payload = b"\x00" * (payload_kb * 1024)
        self.calls: list[Call] = []

    def image_to_video(
        self,
        first_frame: Path,
        output_dir: Path,
        *,
        prompt: str = "",
        last_frame: Path | None = None,
        duration: int = 5,
        resolution: str = "720P",
    ) -> GenerationResult:
        self.calls.append(
            Call(
                "image_to_video",
                prompt,
                {
                    "first_frame": first_frame.name,
                    "last_frame": last_frame.name if last_frame else None,
                    "duration": duration,
                    "resolution": resolution,
                },
            )
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        # 用尾帧名标识动作（VideoGenerator 之后会重命名为 <action>.mp4）
        stem = last_frame.stem if last_frame else first_frame.stem
        target = output_dir / f"{stem}.mp4"
        target.write_bytes(self._payload)
        return GenerationResult(success=True, output_paths=[target])

    def text_to_video(
        self,
        prompt: str,
        output_dir: Path,
        *,
        duration: int = 5,
        resolution: str = "720P",
    ) -> GenerationResult:
        self.calls.append(Call("text_to_video", prompt, {"duration": duration}))
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / "t2v.mp4"
        target.write_bytes(self._payload)
        return GenerationResult(success=True, output_paths=[target])


# ---------------------------------------------------------------------------
# Stage 5：抠图直通
# ---------------------------------------------------------------------------


class PassthroughBackgroundRemover:
    """把帧转成 RGBA 后原样输出，不加载 ONNX 模型。

    真实 `BackgroundRemover` 需要 658 MB 权重 + onnxruntime EP，不适合放进
    每次都跑的回归。它的模型查找、EP 选择、掩码后处理由
    `test_bg_remover.py` 用 mock 单独覆盖。
    """

    def __init__(self, *args, **kwargs) -> None:
        self.calls: list[Path] = []

    def remove_batch(self, frames: list[Path], output_dir: Path) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        out: list[Path] = []
        for frame in frames:
            self.calls.append(frame)
            target = output_dir / frame.name
            with Image.open(frame) as img:
                img.convert("RGBA").save(target, format="PNG")
            out.append(target)
        return out

    def remove_single(self, image_path: Path, output_path: Path) -> Path:
        return self.remove_batch([image_path], output_path.parent)[0]
