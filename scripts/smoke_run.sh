#!/usr/bin/env bash
# GUI 运行期冒烟取证：自造项目 → 构建 → 真实运行 → 存活/日志断言 + 截屏。
#
# 与自动化测试的分工：
#   pytest  验证「生成的源码正确」（契约、素材过管线、编排）——秒级、无 GUI。
#   本脚本  验证「编译出来的程序真的能跑」——需要 cargo 与图形会话，分钟级。
#
# 输入：不依赖任何预置样本。脚本自己用 tests/fixtures 的真实 AI 素材
#       在 build/ 里生成一个项目（默认 sprites_256 录制素材，零 API 调用）。
# 产物：全部落在 build/（已 gitignore），仓库零残留。
#
# 用法:
#   scripts/smoke_run.sh                    # 默认 15s 运行窗口
#   SMOKE_SECONDS=25 scripts/smoke_run.sh
#   SMOKE_PET=MyPet scripts/smoke_run.sh    # 换项目名（影响二进制名）
#
# 产物与构建缓存都在 build/ 下，随时可整目录删除；
# 窗口 <15s 时会跳过「自主行为」断言（首次延迟 10s，太短会 flaky）。
#
# 退出码: 0=冒烟通过；非 0=生成/构建/存活/日志断言失败。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build/smoke"
PET_NAME="${SMOKE_PET:-SmokePet}"
SECONDS_TOTAL="${SMOKE_SECONDS:-15}"   # 需 >10s 才能捕获首次自主行为
CHECKPOINT="${SMOKE_CHECKPOINT:-8}"    # 硬性存活检查点
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$BUILD_DIR/${PET_NAME}_${TIMESTAMP}.log"
SHOT_FILE="$BUILD_DIR/${PET_NAME}_${TIMESTAMP}.png"

# Python 解释器：项目内 .venv → 已激活的 VIRTUAL_ENV → PATH 上的 python3
PY=""
for candidate in \
  "$PROJECT_ROOT/.venv/bin/python" \
  "${VIRTUAL_ENV:-}/bin/python" ; do
  if [[ -x "$candidate" ]]; then PY="$candidate"; break; fi
done
[[ -z "$PY" ]] && PY="$(command -v python3)"
if [[ -z "$PY" ]]; then
  echo "[smoke][FAIL] 找不到 python3；请先按 CONTRIBUTING.md 创建 .venv" >&2
  exit 1
fi

mkdir -p "$BUILD_DIR"
cd "$PROJECT_ROOT"

# 复用构建缓存：项目目录每次都会被生成器整体重建（含 target/），
# 所以把 cargo 产物放到项目外，重复冒烟才是增量构建而非每次 4 分钟全量。
export CARGO_TARGET_DIR="$BUILD_DIR/cargo-target"

# ── 1. 生成项目（用录制的真实 AI 素材，零网络）───────────────────────────
echo "[smoke] 生成项目 $PET_NAME → $BUILD_DIR"
PROJECT_DIR="$("$PY" - "$BUILD_DIR" "$PET_NAME" <<'PYEOF'
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from pet_generator.config import Settings
from pet_generator.runtime_gen import RuntimeGenerator

build_dir, pet_name = Path(sys.argv[1]), sys.argv[2]
fixtures = Path("tests/fixtures/ai_pipeline")
if not (fixtures / "sprites_256" / "manifest.json").exists():
    sys.exit(f"缺少录制素材: {fixtures}")

# 复刻真实管线的阶段目录布局（06_sprites 与同级 01_standard），
# 这样降级图查找走的是与线上一致的路径，而不是测试专用的捏造结构。
stage = build_dir / "stage"
shutil.rmtree(stage, ignore_errors=True)
sprites = stage / "06_sprites"
standard_dir = stage / "01_standard"
shutil.copytree(fixtures / "sprites_256", sprites)
standard_dir.mkdir(parents=True)
shutil.copy(fixtures / "standard.png", standard_dir / "20260801_164236_edited_0.png")

settings = Settings(pet_name=pet_name)
settings.pipeline.output_dir = str(build_dir)
settings.pipeline.no_compile = True
print(RuntimeGenerator(settings).generate(sprites, sprites / "manifest.json"))
PYEOF
)"
PROJECT_DIR="$(printf '%s\n' "$PROJECT_DIR" | tail -1)"
[[ -d "$PROJECT_DIR" ]] || { echo "[smoke][FAIL] 项目生成失败: $PROJECT_DIR" >&2; exit 1; }
echo "[smoke] 项目就绪: $PROJECT_DIR"

# ── 2. 构建 ──────────────────────────────────────────────────────────────
echo "[smoke] cargo build --release ..."
(cd "$PROJECT_DIR" && cargo build --release 2>&1 | tail -3)
BIN="$CARGO_TARGET_DIR/release/$PET_NAME"
if [[ ! -x "$BIN" ]]; then
  echo "[smoke][FAIL] 二进制不存在或不可执行: $BIN" >&2
  exit 1
fi
echo "[smoke] 二进制就绪: $BIN"

# ── 3. 后台运行 ──────────────────────────────────────────────────────────
echo "[smoke] 后台启动 (RUST_LOG=info), 日志 → $LOG_FILE"
RUST_LOG=info "$BIN" >"$LOG_FILE" 2>&1 &
PID=$!
cleanup() {
  if kill -0 "$PID" 2>/dev/null; then kill "$PID" 2>/dev/null || true; fi
}
trap cleanup EXIT

# ── 4. 存活断言 ──────────────────────────────────────────────────────────
sleep "$CHECKPOINT"
if ! kill -0 "$PID" 2>/dev/null; then
  echo "[smoke][FAIL] 进程在 ${CHECKPOINT}s 内退出，日志尾部：" >&2
  tail -20 "$LOG_FILE" >&2
  exit 1
fi
echo "[smoke] 存活检查点通过 (${CHECKPOINT}s)"

# ── 5. 截屏取证（无 GUI 会话时降级为告警）────────────────────────────────
if command -v screencapture >/dev/null 2>&1; then
  screencapture -x "$SHOT_FILE" 2>/dev/null \
    && echo "[smoke] 截屏已保存: $SHOT_FILE" \
    || echo "[smoke][warn] screencapture 失败（可能无 GUI 会话）"
fi

# ── 6. 跑满窗口后优雅退出 ────────────────────────────────────────────────
REMAIN=$(( SECONDS_TOTAL - CHECKPOINT ))
[[ "$REMAIN" -gt 0 ]] && sleep "$REMAIN"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID" 2>/dev/null || true
  wait "$PID" 2>/dev/null || true
  echo "[smoke] 已优雅退出 (运行 ${SECONDS_TOTAL}s)"
else
  echo "[smoke][FAIL] 进程在窗口内异常退出" >&2
  tail -20 "$LOG_FILE" >&2
  exit 1
fi

# ── 7. 日志断言 ──────────────────────────────────────────────────────────
fail=0
# 注意：形如 ${desc}（…）的大括号不可省 —— macOS 自带 bash 3.2 解析 $var 时会把紧跟的
# 多字节字符并入变量名，在 set -u 下会以 unbound variable 静默退出（曾导致断言段整段被跳过）。
assert_log() {
  local pattern="$1" desc="$2" min="${3:-1}"
  local count
  count="$(grep -cE "$pattern" "$LOG_FILE" || true)"
  if [[ "$count" -lt "$min" ]]; then
    echo "[smoke][FAIL] ${desc}（匹配 $count < ${min}）: /$pattern/" >&2
    fail=1
  else
    echo "[smoke] OK ${desc}（匹配 ${count}）"
  fi
}

assert_log "Loaded animation" "多状态动画加载" 5
assert_log "Menu: [0-9]+ rows" "菜单行数已估算"
assert_log "Window placed at" "窗口已定位到锚点"
if grep -qiE "panic|thread '.*' panicked" "$LOG_FILE"; then
  echo "[smoke][FAIL] 日志中出现 panic" >&2
  grep -iE "panic" "$LOG_FILE" | head -5 >&2
  fail=1
else
  echo "[smoke] OK 无 panic"
fi
# 自主行为的首次延迟是 config.rs::BEHAVIOR_FIRST_DELAY_SECS（10s）+ 启动耗时，
# 窗口 <15s 时不足以稳定捕获，此时跳过该断言而不是制造 flaky 失败。
if [[ "$SECONDS_TOTAL" -ge 15 ]]; then
  assert_log "Behavior: playing" "静置后触发自主行为"
fi

if [[ "$fail" -ne 0 ]]; then
  echo "[smoke] 冒烟未通过，日志保留于 $LOG_FILE" >&2
  exit 1
fi
echo "[smoke] 全部断言通过。日志: $LOG_FILE"
