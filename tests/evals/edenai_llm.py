"""Eden AI adapter for deepeval's LLM judge.

Copied from playground/compatibility/deepeval_comp/src/edenai_llm.py
and trimmed to the chat-completions adapter only.
"""

from __future__ import annotations

import openai
from deepeval.models import DeepEvalBaseLLM

DEFAULT_BASE_URL = "https://api.edenai.run"
DEFAULT_MODEL = "openai/gpt-4o"


class _BaseEdenAILLM(DeepEvalBaseLLM):
    """Shared base for Eden AI adapters. Handles client caching and config."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        temperature: float = 0,
        max_tokens: int = 1024,
    ):
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = api_key
        # Don't call super().__init__ — it runs parse_model_name which strips
        # the "provider/" prefix that Eden AI requires.
        self.model_name = model
        self._sync_client = openai.OpenAI(
            api_key=self.api_key, base_url=base_url
        )
        self._async_client = openai.AsyncOpenAI(
            api_key=self.api_key, base_url=base_url
        )

    def get_model_name(self) -> str:
        return self.model_name

    def load_model(self, async_mode: bool = False):
        return self._async_client if async_mode else self._sync_client


class EdenAILLM(_BaseEdenAILLM):
    """Eden AI adapter using chat completions with native structured output."""

    def _chat_kwargs(self, prompt: str, schema: object | None = None) -> dict:
        kwargs = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if schema is not None:
            kwargs["response_format"] = schema
        return kwargs

    def generate(
        self, prompt: str, schema: object | None = None
    ) -> str | object:
        kwargs = self._chat_kwargs(prompt, schema)
        if schema is not None:
            completion = self._sync_client.chat.completions.parse(**kwargs)
            return completion.choices[0].message.parsed
        response = self._sync_client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    async def a_generate(
        self, prompt: str, schema: object | None = None
    ) -> str | object:
        kwargs = self._chat_kwargs(prompt, schema)
        if schema is not None:
            completion = await self._async_client.chat.completions.parse(**kwargs)
            return completion.choices[0].message.parsed
        response = await self._async_client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
