#!/usr/bin/env python3
"""从 ModelScope 获取去背景 ONNX 模型，并做 SHA256 校验。

模型体积远超 Git 单文件上限（u2net 168 MiB、RMBG-2.0 fp16 490 MiB），
因此不入版本库，改由本脚本按需拉取到 ``models/``。

用法::

    python scripts/fetch_models.py                # 拉取缺失的模型（默认全部）
    python scripts/fetch_models.py --model u2net  # 只拉 u2net
    python scripts/fetch_models.py --check        # 只校验本地文件，不下载
    python scripts/fetch_models.py --list         # 打印模型清单与来源
    python scripts/fetch_models.py --force        # 忽略本地文件，重新下载

特性：
- 断点续传（HTTP Range），中断后重跑即接着下；
- 逐块 SHA256 校验，校验失败保留 ``.part`` 并非零退出；
- 镜像/私有源：设 ``MODELSCOPE_ENDPOINT``（默认 ``https://www.modelscope.cn``）。

退出码：0=全部就绪；1=下载或校验失败；2=用法错误。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
DEFAULT_ENDPOINT = "https://www.modelscope.cn"
CHUNK = 1 << 20  # 1 MiB


@dataclass(frozen=True)
class ModelSpec:
    """一个模型的来源与校验信息。

    Attributes:
        key: CLI 使用的短名（与 ``--bg-model`` 取值一致）。
        local_name: 落盘文件名（`bg_remover.py` 按此名查找）。
        repo: ModelScope 模型仓库 ``<org>/<name>``。
        revision: 仓库版本（分支/commit）。
        remote_path: 仓库内文件路径。
        size: 期望字节数。
        sha256: 期望 SHA256（来自 ModelScope 文件元数据，已与本地实测一致）。
        note: 变体说明。
    """

    key: str
    local_name: str
    repo: str
    revision: str
    remote_path: str
    size: int
    sha256: str
    note: str


# 以下 size/sha256 取自 ModelScope 的 repo/files 元数据接口，并与本机既有模型
# 逐字节校验一致（shasum -a 256）。改动来源时务必同步更新这两个字段。
MODELS: tuple[ModelSpec, ...] = (
    ModelSpec(
        key="u2net",
        local_name="u2net.onnx",
        repo="AI-ModelScope/u2net",
        revision="master",
        remote_path="u2net.onnx",
        size=175_997_641,
        sha256="8d10d2f3bb75ae3b6d527c77944fc5e7dcd94b29809d47a739a7a728a912b491",
        note="U2-Net 全精度，速度快，默认模型",
    ),
    ModelSpec(
        key="rmbg",
        local_name="rmbg-2.0.onnx",
        repo="AI-ModelScope/RMBG-2.0",
        revision="master",
        remote_path="onnx/model_fp16.onnx",
        size=513_576_499,
        sha256="9dc47db40d113090ba5d7a13d8fcfd9ee4eda510ce92613219b2fe19da4746f6",
        note="RMBG-2.0 fp16 变体，质量更高但更慢（macOS CoreML 算子覆盖率低）",
    ),
)


def endpoint() -> str:
    return os.environ.get("MODELSCOPE_ENDPOINT", DEFAULT_ENDPOINT).rstrip("/")


def download_url(spec: ModelSpec) -> str:
    query = urllib.parse.urlencode({"Revision": spec.revision, "FilePath": spec.remote_path})
    return f"{endpoint()}/api/v1/models/{spec.repo}/repo?{query}"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def human(size: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GiB"


def verify(spec: ModelSpec, path: Path, *, quiet: bool = False) -> bool:
    """校验本地文件的大小与 SHA256。"""
    if not path.is_file():
        if not quiet:
            print(f"  [缺失] {path}")
        return False
    actual_size = path.stat().st_size
    if actual_size != spec.size:
        print(f"  [大小不符] {path}: {actual_size} != {spec.size}")
        return False
    actual = sha256_of(path)
    if actual != spec.sha256:
        print(f"  [校验失败] {path}\n    实际 {actual}\n    期望 {spec.sha256}")
        return False
    if not quiet:
        print(f"  [OK] {path.name} {human(actual_size)} sha256 匹配")
    return True


def fetch(spec: ModelSpec, dest: Path) -> bool:
    """下载单个模型（支持断点续传），成功返回 True。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    done = part.stat().st_size if part.exists() else 0
    if done > spec.size:
        print(f"  本地 .part 大于期望大小，重新下载: {part}")
        part.unlink()
        done = 0

    url = download_url(spec)
    print(f"  源: {url}")
    if done:
        print(f"  续传自 {human(done)} / {human(spec.size)}")

    request = urllib.request.Request(url, headers={"User-Agent": "desktop-pet-gen/fetch-models"})
    if done:
        request.add_header("Range", f"bytes={done}-")

    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - 固定 https 源
            if done and response.status != 206:
                print("  服务端不支持续传，从头下载")
                done = 0
                part.unlink(missing_ok=True)
            mode = "ab" if done else "wb"
            written = done
            with part.open(mode) as fh:
                while True:
                    block = response.read(CHUNK)
                    if not block:
                        break
                    fh.write(block)
                    written += len(block)
                    pct = written * 100 / spec.size
                    print(
                        f"\r  {human(written)} / {human(spec.size)} ({pct:.1f}%)",
                        end="",
                        flush=True,
                    )
            print()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"\n  [下载失败] {exc}\n  已下载部分保留在 {part}，重跑本脚本可续传")
        return False

    if part.stat().st_size != spec.size:
        print(f"  [不完整] {part.stat().st_size} != {spec.size}，重跑可续传")
        return False

    actual = sha256_of(part)
    if actual != spec.sha256:
        print(f"  [校验失败] sha256 {actual} != {spec.sha256}\n  已保留 {part} 供排查")
        return False

    part.replace(dest)
    print(f"  [完成] {dest} {human(spec.size)}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="从 ModelScope 拉取去背景 ONNX 模型并校验 SHA256",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--model",
        choices=[*(m.key for m in MODELS), "all"],
        default="all",
        help="要处理的模型（默认 all）",
    )
    parser.add_argument("--check", action="store_true", help="只校验本地文件，不下载")
    parser.add_argument("--list", action="store_true", help="打印模型清单与来源后退出")
    parser.add_argument("--force", action="store_true", help="忽略已存在的本地文件，重新下载")
    parser.add_argument(
        "--dest",
        type=Path,
        default=MODELS_DIR,
        help=f"落盘目录（默认 {MODELS_DIR.relative_to(PROJECT_ROOT)}/）",
    )
    args = parser.parse_args(argv)

    selected = [m for m in MODELS if args.model in (m.key, "all")]

    if args.list:
        print(f"ModelScope endpoint: {endpoint()}")
        for spec in selected:
            print(
                f"\n{spec.key}\n"
                f"  仓库    : {spec.repo}@{spec.revision}\n"
                f"  文件    : {spec.remote_path}\n"
                f"  落盘    : {args.dest / spec.local_name}\n"
                f"  大小    : {human(spec.size)}\n"
                f"  sha256  : {spec.sha256}\n"
                f"  说明    : {spec.note}"
            )
        return 0

    failures: list[str] = []
    for spec in selected:
        path = args.dest / spec.local_name
        print(f"\n== {spec.key} ({spec.note}) ==")

        if args.check:
            if not verify(spec, path):
                failures.append(spec.key)
            continue

        if path.exists() and not args.force:
            if verify(spec, path):
                continue
            print("  本地文件不可用，重新下载")
            path.unlink()

        if not fetch(spec, path):
            failures.append(spec.key)

    print()
    if failures:
        print(f"[fetch_models] 未就绪: {', '.join(failures)}")
        if args.check:
            print("提示：运行 `python scripts/fetch_models.py` 拉取缺失模型")
        return 1
    print(f"[fetch_models] 全部就绪（{len(selected)} 个模型）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
