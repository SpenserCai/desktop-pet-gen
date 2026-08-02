# 测试夹具

本目录是**纯数据**，不含代码（合成工厂与假 provider 在 `tests/support/`）。
所有测试只读这里的文件，产物一律写 `tmp_path`，绝不回写夹具。

```
fixtures/
├── portraits/          输入原图（管线入口）
└── ai_pipeline/        真实 AI 产物（录制自一次完整管线运行）
```

## portraits/ — 输入原图

| 文件 | 尺寸 | 用途 |
|------|------|------|
| `figure_anime_a.png` | 857×1200 RGB | 主用输入图（非正方、竖构图） |
| `figure_anime_b.png` | 374×483 RGB | 小尺寸输入图（覆盖低分辨率入口） |

## ai_pipeline/ — 真实 AI 产物（录制）

**来源**：2026-08-01 的一次真实管线运行（`skip_video` 模式）。
Stage 0 用 OpenAI 兼容 Vision，Stage 1/2 用 Azure OpenAI GPT-Image-2，
Stage 6 用 `SpritePacker(frame_size=256)`。

**为什么入库**：真实 AI 素材有合成素材造不出的特性——1024×1024 的 RGB（**无 alpha 通道**，
Stage 5 之前的真实形态）、非居中主体、真实边缘噪声。这些是「素材过管线」回归的唯一可信输入。
体积 5.6 MB，内容不可变（不会 churn）。

**为什么只有这些**：原始录制里 `05_nobg/<action>/` 的两帧就是
`[standard.png, poses/<action>.png]`（md5 逐一核对确认），属于完全重复，
已去重（13.9 MB → 5.6 MB）。需要「逐动作帧目录」的测试由
`tests/support/synth.py::materialize_action_frames()` 在 `tmp_path` 里现搭。

| 路径 | 内容 | 对应阶段 |
|------|------|----------|
| `classification.json` | 真实分类响应（含 `raw_response` 原文） | Stage 0 |
| `standard.png` | 1024×1024 RGB 标准化产物，也是各动作首帧 | Stage 1 |
| `poses/<action>.png` | 10 个动作尾帧，1024×1024 RGB | Stage 2 |
| `sprites_256/*_sheet.png` + `manifest.json` | 10 张横向 sheet（`frame_size=256`，每动作 2 帧）+ manifest | Stage 6 |

动作集：`dance / happy / hungry / idle / look_around / sleep / sleepy / stretch / wave / yawn`
（`humanoid` 体型的完整动作集）。

## 使用约定

- 只读。任何测试若需修改素材，先 `shutil.copy` 到 `tmp_path`。
- 通过 `conftest.py` 的 `ai_assets` / `portraits` fixture 取路径，不要在测试里硬编码相对路径。
- 新增夹具前先问：能不能用 `tests/support/synth.py` 合成？能就别入库。
  只有「真实 AI 产物特性」这一类才值得占版本库空间。
