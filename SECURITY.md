# 安全策略

## 报告漏洞

**请不要用公开 issue 报告安全问题。**

请通过 GitHub 的 [Private vulnerability reporting](https://docs.github.com/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
提交（仓库 Security 页 → Report a vulnerability）。请尽量包含：

- 影响范围与复现步骤；
- 相关版本 / commit；
- 你认为的严重程度与可能的修复方向。

我们会在 **5 个工作日内**确认收到，并在评估后告知处理计划。
修复发布时会在 [CHANGELOG.md](CHANGELOG.md) 中致谢报告者（除非你要求匿名）。

## 支持的版本

项目处于早期阶段，只对 `main` 分支的最新提交提供安全修复。

## 使用者需要知道的安全事项

### 凭据

- 所有 AI 服务凭据**只从环境变量读取**（`AZURE_OPENAI_API_KEY`、`DASHSCOPE_API_KEY` 等，
  完整列表见 [docs/CONFIGURATION.md](docs/CONFIGURATION.md)），仓库里不含任何密钥。
- 不要把 `.env` 提交进版本库（已在 `.gitignore` 中）。
- 日志不会打印凭据，但**会打印 API 端点与模型名**，分享日志前请自行判断。

### 网络行为

- 管线会把你的输入图片上传给你所配置的 AI 服务（图像生成、视频生成、视觉理解）。
  请确认这符合你对该图片的授权范围。
- `scripts/fetch_models.py` 只访问 ModelScope（可用 `MODELSCOPE_ENDPOINT` 改为镜像），
  下载后校验 SHA256。
- **生成出来的桌宠运行时不发起任何网络请求**，也不写任何文件（资产编译期内嵌，状态纯内存）。

### 生成产物

- 生成的 Rust 项目会执行 `cargo build`，即编译并运行本机代码。
  只对你信任的 manifest / sprite 目录运行生成器。
- `manifest.json` 中的动画名会经过 `AnimState` 白名单校验后才注入 Rust 源码，
  非法值在生成阶段就会失败（而不是产出无法编译或行为异常的代码）。
