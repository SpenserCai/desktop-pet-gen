"""统一 CLI 入口 — 纯参数解析 + 调度。

职责：
1. 解析命令行参数（argparse）
2. 构建 Settings 对象（优先级: CLI > 环境变量 > 默认值）
3. 配置 logging
4. 调用 Pipeline(settings).run(input_image)
5. 打印结果摘要

设计取舍：
- CLI 层不包含业务逻辑，仅做参数映射与调度。
- 使用 Settings.from_env() 作为基础，CLI 参数覆盖，保证优先级正确。
- 错误处理统一在 main() 中，异常转为友好的 stderr 消息 + 非零退出码。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from pet_generator import __app_name__, __version__

logger = logging.getLogger(__name__)

# 有效的 body_type 选项
VALID_BODY_TYPES = ("humanoid", "quadruped", "limbless", "object")


def build_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="pet-gen",
        description=(
            f"{__app_name__} v{__version__} — "
            "AI 驱动的桌面宠物精灵动画生成管线。"
            "将单张宠物图片转化为可交互的桌面宠物。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  pet-gen -i cat.png -n my-cat\n"
            "  pet-gen -i dog.png --body-type quadruped --skip-video\n"
            "  pet-gen -i slime.png --body-type limbless --actions idle,bounce,spin\n"
            "  pet-gen -i robot.png --image-provider bailian --video-provider wan27\n"
        ),
    )

    # ─── 必选参数 ─────────────────────────────────────────────────────────
    parser.add_argument(
        "--image",
        "-i",
        type=Path,
        required=True,
        help="输入图片路径（必选）",
    )

    # ─── 可选参数：基础 ───────────────────────────────────────────────────
    parser.add_argument(
        "--name",
        "-n",
        type=str,
        default=None,
        help="宠物名称（默认: my-pet）",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        default=None,
        help="输出目录（默认: ./output）",
    )

    # ─── 可选参数：分类器 ─────────────────────────────────────────────────
    parser.add_argument(
        "--classifier-model",
        type=str,
        default=None,
        help="分类器模型（默认: qwen3.7-plus）",
    )
    parser.add_argument(
        "--classifier-base",
        type=str,
        default=None,
        help="分类器 API base URL",
    )
    parser.add_argument(
        "--body-type",
        type=str,
        choices=VALID_BODY_TYPES,
        default=None,
        help="手动指定体型（跳过 AI 分类）: humanoid | quadruped | limbless | object",
    )

    # ─── 可选参数：Provider 选择 ──────────────────────────────────────────
    parser.add_argument(
        "--image-provider",
        type=str,
        choices=("azure", "bailian"),
        default=None,
        help="图像生成 provider（默认: azure）",
    )
    parser.add_argument(
        "--video-provider",
        type=str,
        choices=("kling", "wan27"),
        default=None,
        help="视频生成 provider（默认: kling）",
    )

    # ─── 可选参数：动作与帧 ───────────────────────────────────────────────
    parser.add_argument(
        "--actions",
        type=str,
        default=None,
        help="动作子集（逗号分隔，如: idle,happy,dance）",
    )
    parser.add_argument(
        "--frame-size",
        type=int,
        default=None,
        help="帧尺寸（默认: 256）",
    )
    parser.add_argument(
        "--bg-model",
        type=str,
        choices=("u2net", "rmbg"),
        default=None,
        help="去背景模型: u2net(快速, 默认) | rmbg(RMBG-2.0, 高质量)",
    )

    # ─── 可选参数：管线控制 ───────────────────────────────────────────────
    parser.add_argument(
        "--skip-video",
        action="store_true",
        default=False,
        help="跳过视频生成（用 2 帧 fallback）",
    )
    parser.add_argument(
        "--no-compile",
        action="store_true",
        default=False,
        help="仅生成 Rust 项目，不编译",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="使用 debug 模式编译（更快，无优化）",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="详细日志输出",
    )

    # ─── 版本 ─────────────────────────────────────────────────────────────
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    return parser


def build_settings(args: argparse.Namespace):
    """从 CLI 参数构建 Settings 对象。

    优先级: CLI args > 环境变量 > 默认值。
    """
    from pet_generator.config import Settings

    # 基础：从环境变量加载（已含默认值）
    settings = Settings.from_env()

    # CLI 覆盖（仅当用户显式传入时）
    if args.name is not None:
        settings.pet_name = args.name
    if args.output_dir is not None:
        settings.pipeline.output_dir = args.output_dir
    if args.classifier_model is not None:
        settings.classifier.model = args.classifier_model
    if args.classifier_base is not None:
        settings.classifier.api_base = args.classifier_base
    if args.body_type is not None:
        settings.body_type_override = args.body_type
    if args.image_provider is not None:
        settings.providers.image_provider = args.image_provider
    if args.video_provider is not None:
        settings.providers.video_provider = args.video_provider
    if args.actions is not None:
        settings.selected_actions = [a.strip() for a in args.actions.split(",") if a.strip()]
    if args.frame_size is not None:
        settings.pipeline.frame_size = args.frame_size
    if args.bg_model is not None:
        settings.pipeline.bg_model = args.bg_model

    # 布尔标志：CLI 显式传入时覆盖
    if args.skip_video:
        settings.pipeline.skip_video = True
    if args.no_compile:
        settings.pipeline.no_compile = True
    if args.debug:
        settings.pipeline.debug_build = True
    if args.verbose:
        settings.pipeline.verbose = True

    return settings


def setup_logging(verbose: bool = False) -> None:
    """配置全局 logging。"""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%H:%M:%S"

    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt=datefmt,
        stream=sys.stderr,
    )

    # 降低第三方库日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> None:
    """CLI 主入口。

    Args:
        argv: 命令行参数列表（None 时使用 sys.argv[1:]）。
    """
    # 强制 stdout/stderr 无缓冲，避免 `| tee` 管道块缓冲导致日志"假死"。
    # 注：对当前进程而言 PYTHONUNBUFFERED 需在解释器启动前生效，故同时建议
    # 用 `python -u -m pet_generator ...` 运行；此处设置主要确保子进程继承该行为。
    os.environ["PYTHONUNBUFFERED"] = "1"

    parser = build_parser()
    args = parser.parse_args(argv)

    # 配置日志
    setup_logging(verbose=args.verbose)

    # 构建配置
    settings = build_settings(args)

    # 输入校验
    input_image: Path = args.image
    if not input_image.exists():
        logger.error("Input image not found: %s", input_image)
        sys.exit(1)

    # 执行管线
    from pet_generator.pipeline import Pipeline

    try:
        pipeline = Pipeline(settings)
        result = pipeline.run(input_image)
    except KeyboardInterrupt:
        logger.warning("Pipeline interrupted by user.")
        sys.exit(130)
    except FileNotFoundError as e:
        logger.error("File not found: %s", e)
        sys.exit(1)
    except RuntimeError as e:
        logger.error("Pipeline failed: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        sys.exit(1)

    # 打印结果摘要
    print()
    print("━" * 50)
    print(f"  ✅ {__app_name__} completed successfully!")
    print(f"  📦 Output: {result}")
    print(f"  🐾 Pet name: {settings.pet_name}")
    if settings.pipeline.no_compile:
        print(f"  📁 Project dir: {result}")
        print(f"  💡 To compile: cd {result} && cargo build --release")
    else:
        print(f"  🚀 Binary: {result}")
        print(f"  💡 Run: {result}")
    print("━" * 50)


if __name__ == "__main__":
    main()
