# 第三方声明

本仓库自身以 [MIT](LICENSE) 授权。以下内容**不随本仓库分发**，
但会在使用过程中被下载或生成，其许可条款独立适用。

## 去背景模型（按需下载）

`scripts/fetch_models.py` 从 ModelScope 拉取以下权重到 `models/`：

| 模型 | 来源 | 许可 |
|------|------|------|
| U^2-Net | [`AI-ModelScope/u2net`](https://www.modelscope.cn/models/AI-ModelScope/u2net) | Apache-2.0，© U^2-Net 作者 |
| RMBG-2.0 (fp16) | [`AI-ModelScope/RMBG-2.0`](https://www.modelscope.cn/models/AI-ModelScope/RMBG-2.0) | 见模型卡；**限制商业使用** |

如果你的用途涉及商业场景，请使用 `--bg-model u2net`（默认值）或自行替换为许可允许的模型。

## AI 生成的素材

管线通过第三方服务（Azure OpenAI GPT-Image、阿里云百炼、Kling 等）生成图像与视频。
生成结果的权利与可用范围由**你与该服务之间的条款**决定，本项目不作任何主张或担保。
输入图片同样受其原始版权约束 —— 请确认你有权将其上传给所选服务处理。

## 测试夹具

`tests/fixtures/` 中的图片仅用于离线回归测试，不参与分发到生成产物中。

## 运行时依赖

生成的桌宠项目依赖 [Bevy](https://bevyengine.org/)（MIT / Apache-2.0 双许可）
与 [image](https://crates.io/crates/image)（MIT / Apache-2.0）；
启用 `tray` 特性时额外依赖 `tray-icon` 与 `muda`（均为 MIT / Apache-2.0）。
完整依赖树见 `pet-runtime/Cargo.lock`。
