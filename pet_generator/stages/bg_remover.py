"""Stage 5: 去背景 — 使用 ONNX 模型移除帧图片背景（双模型 + 跨平台加速）。

将 Stage 4 提取的 RGB 帧转换为 RGBA 透明背景 PNG，
使精灵动画可以叠加在任意桌面背景上。

支持两种去背景模型（通过 ``model_type`` 切换，默认 ``u2net``）:

- ``u2net``  — U2-Net（输入 320×320，体积小、速度快，适合快速测试）
- ``rmbg``   — RMBG-2.0 / BiRefNet（输入 1024×1024，抠图质量更高）

执行后端（Execution Provider）跨平台自动探测:
按优先级 ``CUDA → CoreML → CPU`` 与 onnxruntime 实际可用的 EP 取交集，
并保证 ``CPUExecutionProvider`` 始终位于列表末尾作为兜底。
- Linux / Windows + NVIDIA GPU → 命中 CUDAExecutionProvider
- macOS → 命中 CoreMLExecutionProvider
- 其它 / 无加速硬件 → CPUExecutionProvider 兜底
加载成功后会打印实际启用的 EP 列表。

模型查找顺序（按 ``model_type`` 决定文件名）:
1. 构造函数传入的 ``model_path``（显式指定，不回退）
2. 环境变量: u2net→``U2NET_MODEL_PATH`` / rmbg→``RMBG_MODEL_PATH``
3. 项目目录下 ``models/<filename>``（随项目分发，跨平台）
4. 用户主目录: u2net→``~/.u2net/u2net.onnx`` / rmbg→``~/.rmbg/rmbg-2.0.onnx``

如果所有路径均不可用，或推理失败，降级为不去背景（直接复制原图），并打印警告。

依赖:
- numpy, Pillow, onnxruntime（已在 .venv 中安装，无新增依赖）
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# ImageNet 标准化参数（两个模型共用）
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# EP 优先级（加速优先，CPU 兜底）
_EP_PRIORITY = [
    "CUDAExecutionProvider",  # Linux / Windows + NVIDIA GPU
    "CoreMLExecutionProvider",  # macOS
    "CPUExecutionProvider",  # 兜底
]

# 各模型的发现/推理规格
_MODEL_SPECS: dict[str, dict] = {
    "u2net": {
        "label": "U2-Net",
        "filename": "u2net.onnx",
        "env_var": "U2NET_MODEL_PATH",
        "home_subdir": ".u2net",
        "input_size": (320, 320),
    },
    "rmbg": {
        "label": "RMBG-2.0",
        "filename": "rmbg-2.0.onnx",
        "env_var": "RMBG_MODEL_PATH",
        "home_subdir": ".rmbg",
        "input_size": (1024, 1024),
    },
}


def _build_providers() -> list[str]:
    """跨平台自动探测 ONNX Runtime Execution Provider。

    按 ``CUDA → CoreML → CPU`` 优先级与 onnxruntime 可用 EP 取交集，
    并保证 ``CPUExecutionProvider`` 始终位于末尾作为兜底。

    Returns:
        有序的 EP 列表（至少包含 CPUExecutionProvider）。
    """
    import onnxruntime as ort

    available = set(ort.get_available_providers())

    # 加速 EP 按优先级排在前（不含 CPU）
    providers = [ep for ep in _EP_PRIORITY if ep != "CPUExecutionProvider" and ep in available]
    # CPU 兜底，总在最后
    if "CPUExecutionProvider" in available:
        providers.append("CPUExecutionProvider")

    if not providers:  # 理论上不会发生，onnxruntime 必带 CPU EP
        providers = ["CPUExecutionProvider"]

    return providers


def _find_model_path(model_type: str, explicit_path: Path | None = None) -> Path | None:
    """按优先级查找指定模型的 ONNX 文件。

    当显式传入 ``explicit_path`` 时，仅检查该路径（不回退到其他候选）；
    为 None 时依次检查环境变量、项目目录、用户主目录。

    Args:
        model_type: ``u2net`` 或 ``rmbg``。
        explicit_path: 显式模型路径（可选）。

    Returns:
        模型路径，全部不存在时返回 None。
    """
    spec = _MODEL_SPECS[model_type]
    label = spec["label"]

    # 1. 构造函数显式传入 — 仅检查此路径，不回退
    if explicit_path is not None:
        if explicit_path.is_file():
            logger.info("找到 %s 模型（显式指定）: %s", label, explicit_path)
            return explicit_path
        logger.debug("显式指定的模型路径不存在: %s", explicit_path)
        return None

    # 2~4: 自动查找候选列表
    candidates: list[Path] = []

    # 2. 环境变量
    env_path = os.environ.get(spec["env_var"])
    if env_path:
        candidates.append(Path(env_path))

    # 3. 项目目录下 models/<filename>（相对于本文件向上两级 = 项目根 desktop-pet-gen）
    project_root = Path(__file__).resolve().parent.parent.parent
    candidates.append(project_root / "models" / spec["filename"])

    # 4. 用户主目录 ~/.<home_subdir>/<filename>
    candidates.append(Path.home() / spec["home_subdir"] / spec["filename"])

    for path in candidates:
        if path.is_file():
            logger.info("找到 %s 模型: %s", label, path)
            return path

    logger.debug(
        "%s 模型未找到，已搜索路径: %s",
        label,
        [str(p) for p in candidates],
    )
    return None


class BackgroundRemover:
    """Stage 5 — ONNX 去背景（支持 U2-Net 与 RMBG-2.0）。

    Args:
        model_type: 去背景模型，``"u2net"``（默认，快速）或 ``"rmbg"``
            （RMBG-2.0，高质量）。非法值抛出 ``ValueError``。
        model_path: 显式指定模型路径；为 None 时按默认顺序查找。
    """

    def __init__(
        self,
        model_type: str = "u2net",
        model_path: Path | None = None,
    ) -> None:
        if model_type not in _MODEL_SPECS:
            raise ValueError(
                f"不支持的去背景模型 model_type={model_type!r}，可选值: {sorted(_MODEL_SPECS)}"
            )

        self._model_type = model_type
        self._spec = _MODEL_SPECS[model_type]
        self._session = None
        self._model_path = _find_model_path(model_type, model_path)

        if self._model_path is not None:
            try:
                import onnxruntime as ort

                providers = _build_providers()
                self._session = ort.InferenceSession(
                    str(self._model_path),
                    providers=providers,
                )
                logger.info(
                    "%s ONNX 模型已加载: %s | 请求 EP: %s | 实际启用 EP: %s",
                    self._spec["label"],
                    self._model_path,
                    providers,
                    self._session.get_providers(),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "%s 模型加载失败，将降级为不去背景: %s",
                    self._spec["label"],
                    exc,
                )
                self._session = None
        else:
            logger.warning(
                "%s 模型文件未找到，将降级为不去背景（直接复制原图）。"
                "可设置环境变量 %s 或放置模型到项目 models/ 目录。",
                self._spec["label"],
                self._spec["env_var"],
            )

    @property
    def is_available(self) -> bool:
        """模型是否可用。"""
        return self._session is not None

    # -- 公开接口 ----------------------------------------------------------

    def remove_batch(self, frames: list[Path], output_dir: Path) -> list[Path]:
        """批量去背景。

        Args:
            frames: 输入帧路径列表。
            output_dir: 输出目录（不存在时自动创建）。

        Returns:
            去背景后的 RGBA PNG 路径列表（与输入一一对应）。
            模型不可用时直接复制原图。
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        results: list[Path] = []
        total = len(frames)

        logger.info("去背景: %d 帧 → %s", total, output_dir)
        for i, frame_path in enumerate(frames):
            output_path = output_dir / frame_path.name
            self.remove_single(frame_path, output_path)
            results.append(output_path)
            # 每 10 帧或末尾打印一次进度，避免长时静默
            if (i + 1) % 10 == 0 or (i + 1) == total:
                logger.info("  去背景进度: %d/%d 帧", i + 1, total)

        logger.info("批量去背景完成: %d 帧", len(results))
        return results

    def remove_single(self, image_path: Path, output_path: Path) -> Path:
        """单张去背景。

        Args:
            image_path: 输入图片路径。
            output_path: 输出 RGBA PNG 路径。

        Returns:
            输出路径（与 output_path 相同）。
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if self._session is None:
            # 降级：直接复制原图
            shutil.copy2(image_path, output_path)
            return output_path

        try:
            self._remove_bg(image_path, output_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("去背景失败，复制原图: %s → %s (%s)", image_path, output_path, exc)
            shutil.copy2(image_path, output_path)

        return output_path

    # -- 内部方法 ----------------------------------------------------------

    def _remove_bg(self, image_path: Path, output_path: Path) -> None:
        """按 model_type 分发到对应模型的推理实现。"""
        if self._model_type == "rmbg":
            self._remove_bg_rmbg(image_path, output_path)
        else:
            self._remove_bg_u2net(image_path, output_path)

    def _remove_bg_u2net(self, image_path: Path, output_path: Path) -> None:
        """U2-Net 推理（输入 320×320）。"""
        assert self._session is not None

        img = Image.open(image_path).convert("RGB")
        original_size = img.size  # (W, H)

        arr = self._preprocess(img, self._spec["input_size"])

        input_name = self._session.get_inputs()[0].name
        result = self._session.run(None, {input_name: arr})
        mask = self._squeeze_mask(result[0])

        self._save_rgba(img, mask, original_size, output_path)

    def _remove_bg_rmbg(self, image_path: Path, output_path: Path) -> None:
        """RMBG-2.0 (BiRefNet) 推理（输入 1024×1024，输出 alpha mask）。"""
        assert self._session is not None

        img = Image.open(image_path).convert("RGB")
        original_size = img.size  # (W, H)

        arr = self._preprocess(img, self._spec["input_size"])

        # RMBG-2.0 ONNX 输入名 pixel_values [1,3,H,W]，输出名 alphas [1,1,H,W]
        input_name = self._session.get_inputs()[0].name
        result = self._session.run(None, {input_name: arr})
        mask = self._squeeze_mask(result[0])

        self._save_rgba(img, mask, original_size, output_path)

    # -- 预处理 / 后处理工具 ------------------------------------------------

    @staticmethod
    def _preprocess(img: Image.Image, input_size: tuple[int, int]) -> np.ndarray:
        """统一预处理: resize → /255 → ImageNet 归一化 → NCHW float32。"""
        img_resized = img.resize(input_size, Image.BILINEAR)
        arr = np.array(img_resized).astype(np.float32) / 255.0
        arr = (arr - _MEAN) / _STD
        arr = arr.transpose(2, 0, 1)[np.newaxis, ...]  # (1, 3, H, W)
        return arr

    @staticmethod
    def _squeeze_mask(raw: np.ndarray) -> np.ndarray:
        """将模型输出压缩为 2D float mask (H, W)。

        兼容 [1,1,H,W] / [1,H,W] / [H,W] 等形状。
        """
        mask = raw[0]  # 取第一个 batch
        if mask.ndim == 3:  # (C, H, W) → 取第一通道
            mask = mask[0]
        return mask

    @staticmethod
    def _save_rgba(
        img: Image.Image,
        mask: np.ndarray,
        original_size: tuple[int, int],
        output_path: Path,
    ) -> None:
        """统一后处理: min-max 归一化 → uint8 → resize 回原尺寸 → putalpha → 保存 PNG。"""
        mask = mask.astype(np.float32)
        mask_min = mask.min()
        mask_max = mask.max()
        mask = (mask - mask_min) / (mask_max - mask_min + 1e-8)
        mask = (mask * 255).astype(np.uint8)

        mask_img = Image.fromarray(mask, mode="L").resize(original_size, Image.LANCZOS)

        img_rgba = img.convert("RGBA")
        img_rgba.putalpha(mask_img)
        img_rgba.save(output_path, format="PNG")
