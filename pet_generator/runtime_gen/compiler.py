"""cargo build 封装 — 编译生成的 Rust 桌面宠物项目。

设计取舍：
- 抑制编译输出，只在出错时显示最后 2000 字符的 stderr，
  防止大量编译日志撑爆上层调用方的上下文窗口。
- 通过环境变量继承 + CARGO_TERM_COLOR=never 确保输出可解析。
- 返回二进制路径，由调用方决定后续操作（运行 / 打包 / 分发）。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def compile_project(
    project_dir: Path,
    release: bool = True,
    verbose: bool = False,
) -> Path:
    """编译 Rust 桌面宠物项目。

    Args:
        project_dir: 包含 Cargo.toml 的项目根目录。
        release: True 使用 ``--release`` 优化编译，False 使用 debug 编译（更快）。
        verbose: 是否在 debug 级别记录编译输出。

    Returns:
        编译产物的二进制文件路径。

    Raises:
        FileNotFoundError: cargo 不在 PATH 中。
        RuntimeError: 编译失败（附带截断的 stderr）。
    """
    cargo = shutil.which("cargo")
    if cargo is None:
        raise FileNotFoundError(
            "cargo not found in PATH. Please install Rust toolchain: https://rustup.rs/"
        )

    cmd: list[str] = [cargo, "build"]
    if release:
        cmd.append("--release")

    # 继承当前环境变量，禁用彩色输出以便日志解析
    env = os.environ.copy()
    env["CARGO_TERM_COLOR"] = "never"

    logger.info(
        "Compiling Rust project: %s (%s mode)",
        project_dir,
        "release" if release else "debug",
    )

    result = subprocess.run(
        cmd,
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        env=env,
        timeout=600,  # 10 分钟编译超时保护
        stdin=subprocess.DEVNULL,  # 切断 stdin 继承，防止 cargo 读 stdin 阻塞
    )

    if result.returncode != 0:
        # 只显示最后 2000 字符的 stderr，避免上下文爆炸
        error_tail = result.stderr[-2000:] if result.stderr else "(no stderr)"
        raise RuntimeError(
            f"Rust compilation failed (exit code {result.returncode}):\n{error_tail}"
        )

    if verbose:
        logger.debug("cargo stderr (tail): %s", result.stderr[-500:] if result.stderr else "")

    # 确定二进制路径
    profile_dir = "release" if release else "debug"
    # 从 Cargo.toml 解析 package name（fallback: 目录名）
    package_name = _parse_package_name(project_dir)
    binary_path = project_dir / "target" / profile_dir / package_name

    if not binary_path.exists():
        # macOS/Linux 无后缀；若不存在则尝试列出 target 目录辅助诊断
        target_dir = project_dir / "target" / profile_dir
        available = (
            [f.name for f in target_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
            if target_dir.exists()
            else []
        )
        raise RuntimeError(
            f"Expected binary not found: {binary_path}\n"
            f"Available files in {target_dir}: {available[:20]}"
        )

    logger.info("Compilation successful: %s", binary_path)
    return binary_path


def _parse_package_name(project_dir: Path) -> str:
    """从 Cargo.toml 解析 [package] name。

    简单行解析，避免引入 toml 依赖。
    Fallback: 使用目录名。
    """
    cargo_toml = project_dir / "Cargo.toml"
    if not cargo_toml.exists():
        return project_dir.name

    in_package_section = False
    for line in cargo_toml.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "[package]":
            in_package_section = True
            continue
        if stripped.startswith("[") and in_package_section:
            break  # 进入下一个 section
        if in_package_section and stripped.startswith("name"):
            # name = "desktop-pet"
            parts = stripped.split("=", 1)
            if len(parts) == 2:
                return parts[1].strip().strip('"').strip("'")

    return project_dir.name
