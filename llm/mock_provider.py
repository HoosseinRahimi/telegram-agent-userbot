"""
Offline Deterministic Mock LLM Provider.

Provides an offline LLM provider for unit/integration testing and local
development with zero network overhead, no API keys, and deterministic outputs.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from .base import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
)


class MockLLMProvider(BaseLLMProvider):
    """
    Offline mock provider returning predictable responses for testing and development.
    """

    def __init__(
        self,
        default_response: str = "پاسخ شبیه‌سازی‌شده توسط مدل زبانی ایجنت.",
        model_name: str = "mock-agent-v1",
        simulated_delay: float = 0.0,
        fail_with: Exception | None = None,
        custom_responder: Callable[[LLMRequest], str] | None = None,
    ) -> None:
        self.default_response = default_response
        self.model_name = model_name
        self.simulated_delay = simulated_delay
        self.fail_with = fail_with
        self.custom_responder = custom_responder
        self.call_history: list[LLMRequest] = []

    @property
    def last_request(self) -> LLMRequest | None:
        return self.call_history[-1] if self.call_history else None

    @property
    def provider_name(self) -> str:
        return "mock"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Processes an LLMRequest and returns a predictable LLMResponse.
        """
        self.call_history.append(request)

        if self.simulated_delay > 0:
            await asyncio.sleep(self.simulated_delay)

        if self.fail_with is not None:
            raise self.fail_with

        # Custom responder callback if provided
        if self.custom_responder:
            text = self.custom_responder(request)
        else:
            user_text = request.prompt or ""
            # If the request contains messages, extract the latest user message
            if not user_text and request.messages:
                for m in reversed(request.messages):
                    if m.role == "user":
                        user_text = m.content
                        if "<untrusted_user_input>" in user_text:
                            inner = user_text.split("<untrusted_user_input>")[1].split("</untrusted_user_input>")[0].strip()
                            if inner:
                                user_text = inner
                        break

            # Handle summary requests intuitively
            if "خلاصه" in user_text or "summary" in user_text.lower() or "digest" in user_text.lower():
                text = (
                    "📊 **گزارش خلاصه پیام‌ها:**\n\n"
                    "• نکات کلیدی استخراج‌شده از تاریخچه پیام‌ها\n"
                    "• رویدادها و اخبار مهم ثبت‌شده\n"
                    "• جمع‌بندی موضوعی توسط ایجنت هوشمند"
                )
            else:
                text = f"{self.default_response} [پاسخ به: {user_text[:50]}...]" if user_text else self.default_response

        return LLMResponse(
            content=text,
            model=self.model_name,
            tokens_used=len(text.split()),
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": len(text.split()), "total_tokens": 10 + len(text.split())},
        )
