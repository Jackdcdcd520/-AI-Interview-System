# -*- coding: utf-8 -*-
"""AI 子包：统一的 Provider 抽象（mock / deepseek）。"""
from .provider import (  # noqa: F401
    AIProviderError,
    BaseAIProvider,
    DeepSeekAIProvider,
    MockAIProvider,
    available_providers,
    get_provider,
)

__all__ = [
    "AIProviderError",
    "BaseAIProvider",
    "DeepSeekAIProvider",
    "MockAIProvider",
    "available_providers",
    "get_provider",
]
