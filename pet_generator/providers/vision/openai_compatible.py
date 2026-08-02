"""通用 OpenAI SDK 视觉理解 Provider。

使用 openai Python SDK 调用任何 OpenAI 兼容的视觉模型（DashScope Qwen-VL、Azure 等）。
- describe(): 自由文本描述
- classify(): JSON mode 结构化输出 + 自动重试

特性:
- 图片自动转 base64 data URL
- classify() 使用 response_format={"type": "json_object"} 保证 JSON 输出
- 超时 / JSON 解析失败 → 指数退避重试
- 通过 ClassifierSettings 注入配置，不硬编码

环境变量（由 ClassifierSettings.api_key_env 指定）:
    DASHSCOPE_API_KEY: 百炼 API 密钥（默认）
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from openai import APITimeoutError, OpenAI

from pet_generator.config.settings import ClassifierSettings
from pet_generator.providers.base import VisionProvider
from pet_generator.providers.vision.base import image_to_data_url

logger = logging.getLogger(__name__)


class OpenAICompatibleVisionProvider(VisionProvider):
    """通用 OpenAI SDK 视觉理解 Provider。

    兼容所有 OpenAI API 格式的视觉模型端点。

    Args:
        settings: 分类器配置（model, api_base, api_key_env, temperature 等）
    """

    def __init__(self, settings: ClassifierSettings | None = None) -> None:
        self._settings = settings or ClassifierSettings()
        self._client: OpenAI | None = None

    @property
    def _get_client(self) -> OpenAI:
        """延迟初始化 OpenAI 客户端。"""
        if self._client is None:
            self._client = OpenAI(
                api_key=self._settings.api_key,
                base_url=self._settings.api_base,
                timeout=self._settings.timeout,
            )
        return self._client

    def describe(self, image_path: Path, prompt: str = "Describe this image in detail.") -> str:
        """对图片进行视觉理解，返回文本描述。

        Args:
            image_path: 图片路径
            prompt: 引导提示词

        Returns:
            文本描述。失败时返回 "[Vision Error] ..." 格式。
        """
        try:
            data_url = image_to_data_url(image_path)

            response = self._get_client.chat.completions.create(
                model=self._settings.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": data_url}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                max_tokens=self._settings.max_tokens,
                temperature=self._settings.temperature,
            )

            content = response.choices[0].message.content
            return content or ""

        except FileNotFoundError as e:
            return f"[Vision Error] {e}"
        except APITimeoutError:
            return f"[Vision Error] Request timed out after {self._settings.timeout}s"
        except Exception as e:
            logger.exception("Vision describe failed")
            return f"[Vision Error] {type(e).__name__}: {e}"

    def classify(
        self,
        image_path: Path,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        """结构化分类 — JSON mode + 指数退避重试。

        Args:
            image_path: 图片路径
            system_prompt: 系统提示词（定义分类规则与输出 Schema）
            user_prompt: 用户提示词

        Returns:
            解析后的 JSON 字典。失败时返回 {"error": "..."} 格式。
        """
        last_error = ""

        for attempt in range(self._settings.max_retries + 1):
            if attempt > 0:
                # 指数退避: 1s, 2s, 4s...
                wait = 2 ** (attempt - 1)
                logger.info(
                    "Classify retry %d/%d after %ds (prev error: %s)",
                    attempt,
                    self._settings.max_retries,
                    wait,
                    last_error,
                )
                time.sleep(wait)

            try:
                data_url = image_to_data_url(image_path)

                response = self._get_client.chat.completions.create(
                    model=self._settings.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": data_url}},
                                {"type": "text", "text": user_prompt},
                            ],
                        },
                    ],
                    max_tokens=self._settings.max_tokens,
                    temperature=self._settings.temperature,
                    response_format={"type": "json_object"},
                )

                content = response.choices[0].message.content
                if not content:
                    last_error = "Empty response content"
                    continue

                # 解析 JSON
                result = json.loads(content)
                if not isinstance(result, dict):
                    last_error = f"Expected JSON object, got {type(result).__name__}"
                    continue

                return result

            except FileNotFoundError as e:
                # 文件不存在无需重试
                return {"error": str(e)}
            except json.JSONDecodeError as e:
                last_error = f"JSON parse failed: {e}"
                logger.warning("Classify JSON parse error (attempt %d): %s", attempt + 1, e)
                continue
            except APITimeoutError:
                last_error = f"Request timed out after {self._settings.timeout}s"
                logger.warning("Classify timeout (attempt %d)", attempt + 1)
                continue
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.exception("Classify unexpected error (attempt %d)", attempt + 1)
                continue

        # 所有重试耗尽
        logger.error(
            "Classify failed after %d attempts: %s", self._settings.max_retries + 1, last_error
        )
        return {
            "error": f"All {self._settings.max_retries + 1} attempts failed. Last: {last_error}"
        }
