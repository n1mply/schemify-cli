from __future__ import annotations

import json
import logging
from typing import Mapping

import os

try:
    from openai import AuthenticationError, OpenAI
except ImportError:  # openai не установлен: хуманизация через ИИ просто отключится
    OpenAI = None  # type: ignore[assignment]

    class AuthenticationError(Exception):  # type: ignore[no-redef]
        pass

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.intelligence.io.solutions/api/v1"
DEFAULT_MODELS = ["Qwen/Qwen3-Next-80B-A3B-Instruct", "deepseek-ai/DeepSeek-V4-Flash-0731"]


def _load_settings() -> dict:
    """Настройки ИИ из переменных окружения (их заполняет .env, см. main.py)."""
    models = [m.strip() for m in os.getenv("LLM_MODELS", "").split(",") if m.strip()]
    try:
        timeout = float(os.getenv("LLM_TIMEOUT", "") or 20.0)
    except ValueError:
        timeout = 20.0
    return {
        "api_key": os.getenv("LLM_API_KEY", "").strip(),
        "base_url": os.getenv("LLM_BASE_URL", "").strip() or DEFAULT_BASE_URL,
        "timeout": timeout,
        "models": models or list(DEFAULT_MODELS),
    }

SYSTEM_PROMPT = """Ты — модуль нормализации и хуманизации текстов для учебных блок-схем по ГОСТ 19.701-90.
Твоя задача — преобразовать фрагменты кода C в лаконичные фразы на русском языке.

Правила формулировок:
1. Ввод/вывод:
   - scanf(...) -> "Ввод: a, b"
   - printf("Текст\\n") -> 'Вывод: "Текст"'
   - Если printf выводит формулу/значения -> 'Вывод: <смысл выражения>'
2. Вычисления и процессы:
   - sum += value -> "sum = sum + value"
   - count++ -> "count = count + 1"
   - Сложные тернарники: краткое условие и результат (например: "cell = '+' если сумма четная, иначе '-'")
3. Условия (символ «Решение»):
   - Убирай шум C (лишние скобки, != 1, == 0).
   - Сформулируй краткий вопрос: например, "Размеры <= 0 или ошибка ввода?" вместо "scanf(...) != 2 || height <= 0 || width <= 0"
4. Ограничения:
   - Максимум 1-3 коротких строки на блок.
   - Отвечай СТРОГО в формате валидного JSON-объекта, где ключи — переданные ID нод, а значения — хуманизированный текст.
"""


class LLMHumanizerClient:
    """Клиент с поддержкой каскадного переключения моделей (failover)."""

    def __init__(self) -> None:
        cfg = _load_settings()
        self.api_key = cfg["api_key"]
        self.base_url = cfg["base_url"]
        self.timeout = cfg["timeout"]
        self.models: list[str] = cfg["models"]

        self._client = None
        if self.api_key and OpenAI is not None:
            try:
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=self.timeout,
                    max_retries=0,  # Отключаем внутренние ретраи, чтобы быстро переключиться на следующую модель
                )
            except Exception as exc:
                logger.warning("Ошибка инициализации OpenAI клиента: %s", exc)

    def humanize_batch(self, nodes: Mapping[str, str]) -> dict[str, str]:
        """Пакетно хуманизирует ноды с перебором резервных моделей.

        Если ни одна модель не ответила, возвращает пустой словарь {},
        чтобы исходный код нод остался без изменений.
        """
        if not nodes or not self._client or not self.models:
            return {}

        payload_json = json.dumps(nodes, ensure_ascii=False)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Хуманизируй следующие блоки кода блок-схемы:\n{payload_json}",
            },
        ]

        total_models = len(self.models)

        for index, model_name in enumerate(self.models):
            try:
                logger.info(
                    "Попытка хуманизации [%d/%d] через модель: %s",
                    index + 1,
                    total_models,
                    model_name,
                )

                response = self._client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    timeout=self.timeout,
                )

                # В SDK ответ лежит в choices[0]
                if not response.choices:
                    raise ValueError("Модель вернула пустой список choices.")

                raw_content = response.choices[0].message.content or "{}"
                result = json.loads(raw_content)

                if isinstance(result, dict) and result:
                    logger.info("Модель %s успешно вернула результат.", model_name)
                    return {
                        str(k): str(v).strip()
                        for k, v in result.items()
                        if str(v).strip()
                    }

                raise ValueError("Модель вернула некорректный или пустой JSON.")

            except AuthenticationError as e:
                # Если ключ в принципе невалиден, продолжать перебор бессмысленно
                logger.error("Критическая ошибка авторизации io.net (проверьте LLM_API_KEY): %s", e)
                break

            except Exception as exc:
                error_type = type(exc).__name__
                logger.warning(
                    "Модель %s недоступна или вернула ошибку (%s: %s).",
                    model_name,
                    error_type,
                    exc,
                )

                # Проверяем, есть ли следующая резервная модель
                if index + 1 < total_models:
                    next_model = self.models[index + 1]
                    logger.info("Переключаемся на резервную модель -> %s", next_model)
                else:
                    logger.error(
                        "Все модели из списка LLM_MODELS исчерпаны или недоступны. "
                        "Оставляем исходный код блоков без изменений."
                    )

        return {}