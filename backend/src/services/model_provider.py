"""Service for fetching and managing AI model providers."""

from __future__ import annotations

import logging
from typing import List, Optional
import httpx
from functools import lru_cache

from ..models.settings import ModelInfo, ModelProvider

logger = logging.getLogger(__name__)

# Hardcoded Google models
GOOGLE_MODELS = [
    ModelInfo(
        id="gemini-2.0-flash-exp",
        name="Gemini 2.0 Flash (Experimental)",
        provider=ModelProvider.GOOGLE,
        is_free=True,
        supports_thinking=False,
        context_length=1000000,
        description="Latest experimental Gemini model with 1M token context"
    ),
    ModelInfo(
        id="gemini-1.5-pro",
        name="Gemini 1.5 Pro",
        provider=ModelProvider.GOOGLE,
        is_free=False,
        supports_thinking=False,
        context_length=2000000,
        description="Advanced Gemini model with 2M token context"
    ),
    ModelInfo(
        id="gemini-1.5-flash",
        name="Gemini 1.5 Flash",
        provider=ModelProvider.GOOGLE,
        is_free=True,
        supports_thinking=False,
        context_length=1000000,
        description="Fast and efficient Gemini model"
    ),
]

# Priority models to always include in the list (regardless of free status)
# These are popular models users likely want quick access to
PRIORITY_OPENROUTER_MODELS = {
    # Free models
    "deepseek/deepseek-chat:free",
    "deepseek/deepseek-r1:free",
    "google/gemini-2.0-flash-exp:free",
    "google/gemini-2.5-flash-preview-05-20:free",
    "google/gemini-2.0-flash-thinking-exp:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen-2.5-72b-instruct:free",
    # Premium models (will be marked as not free)
    "anthropic/claude-sonnet-4",
    "anthropic/claude-4-opus",
    "openai/gpt-4.1",
    "openai/o3",
    "google/gemini-2.5-pro-preview",
    "deepseek/deepseek-r1",
    "x-ai/grok-3-beta",
}

# Fallback models when OpenRouter API is unavailable
FALLBACK_OPENROUTER_MODELS = [
    ModelInfo(
        id="deepseek/deepseek-chat",
        name="DeepSeek Chat",
        provider=ModelProvider.OPENROUTER,
        is_free=True,
        supports_thinking=False,
        context_length=128000,
        description="DeepSeek's powerful chat model"
    ),
    ModelInfo(
        id="deepseek/deepseek-r1",
        name="DeepSeek R1",
        provider=ModelProvider.OPENROUTER,
        is_free=True,
        supports_thinking=True,
        context_length=128000,
        description="DeepSeek's reasoning model with extended thinking"
    ),
    ModelInfo(
        id="google/gemini-2.0-flash-exp:free",
        name="Gemini 2.0 Flash (Free via OpenRouter)",
        provider=ModelProvider.OPENROUTER,
        is_free=True,
        supports_thinking=False,
        context_length=1000000,
        description="Google's Gemini 2.0 Flash via OpenRouter free tier"
    ),
    ModelInfo(
        id="google/gemini-2.0-flash-thinking-exp:free",
        name="Gemini 2.0 Flash Thinking (Free)",
        provider=ModelProvider.OPENROUTER,
        is_free=True,
        supports_thinking=True,
        context_length=1000000,
        description="Gemini 2.0 with thinking mode via OpenRouter"
    ),
    ModelInfo(
        id="meta-llama/llama-3.3-70b-instruct",
        name="Llama 3.3 70B Instruct",
        provider=ModelProvider.OPENROUTER,
        is_free=True,
        supports_thinking=False,
        context_length=131072,
        description="Meta's latest Llama model with 70B parameters"
    ),
    ModelInfo(
        id="qwen/qwen-2.5-72b-instruct",
        name="Qwen 2.5 72B Instruct",
        provider=ModelProvider.OPENROUTER,
        is_free=True,
        supports_thinking=False,
        context_length=131072,
        description="Alibaba's Qwen 2.5 large model"
    ),
]


class ModelProviderService:
    """Service for fetching models from various providers."""

    OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
    CACHE_TTL_SECONDS = 300  # 5 minutes

    def __init__(self, openrouter_api_key: Optional[str] = None):
        """
        Initialize the model provider service.

        Args:
            openrouter_api_key: Optional OpenRouter API key for authenticated requests
        """
        self.openrouter_api_key = openrouter_api_key

    async def get_openrouter_models(self) -> List[ModelInfo]:
        """
        Fetch available models from OpenRouter API.

        Returns:
            List of ModelInfo objects for free models and priority models
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {}
                if self.openrouter_api_key:
                    headers["Authorization"] = f"Bearer {self.openrouter_api_key}"

                response = await client.get(
                    f"{self.OPENROUTER_API_BASE}/models",
                    headers=headers
                )
                response.raise_for_status()
                data = response.json()

                models = []
                for model_data in data.get("data", []):
                    model_id = model_data.get("id", "")

                    # Check actual pricing to determine if model is free
                    # Free models have both prompt and completion cost of "0"
                    # OR have :free suffix in model ID
                    pricing = model_data.get("pricing", {})
                    prompt_price = str(pricing.get("prompt", "1"))
                    completion_price = str(pricing.get("completion", "1"))

                    is_free = (
                        ":free" in model_id.lower()
                        or (prompt_price == "0" and completion_price == "0")
                    )

                    # Include model if it's free OR in priority list
                    is_priority = model_id in PRIORITY_OPENROUTER_MODELS
                    if not is_free and not is_priority:
                        continue

                    # Check if model supports thinking mode
                    # Models with :thinking suffix or "reasoning" in name
                    supports_thinking = (
                        ":thinking" in model_id.lower()
                        or "reasoning" in model_data.get("name", "").lower()
                        or "/r1" in model_id.lower()
                        or "/o1" in model_id.lower()
                        or "/o3" in model_id.lower()
                    )

                    models.append(ModelInfo(
                        id=model_id,
                        name=model_data.get("name", model_id),
                        provider=ModelProvider.OPENROUTER,
                        is_free=is_free,  # Actual free status, not just inclusion
                        supports_thinking=supports_thinking,
                        context_length=model_data.get("context_length"),
                        description=model_data.get("description")
                    ))

                # Sort by priority models first, then alphabetically
                models.sort(
                    key=lambda m: (
                        m.id not in PRIORITY_OPENROUTER_MODELS,
                        m.name.lower()
                    )
                )

                logger.info(f"Fetched {len(models)} models from OpenRouter")
                return models

        except httpx.HTTPError as e:
            logger.warning(f"Failed to fetch OpenRouter models, using fallback: {e}")
            return FALLBACK_OPENROUTER_MODELS.copy()
        except Exception as e:
            logger.warning(f"Unexpected error fetching OpenRouter models, using fallback: {e}")
            return FALLBACK_OPENROUTER_MODELS.copy()

    def get_google_models(self) -> List[ModelInfo]:
        """
        Get hardcoded Google models.

        Returns:
            List of Google ModelInfo objects
        """
        return GOOGLE_MODELS.copy()

    async def get_all_models(self) -> List[ModelInfo]:
        """
        Get all available models from all providers.

        Returns:
            Combined list of ModelInfo objects from all providers
        """
        google_models = self.get_google_models()
        openrouter_models = await self.get_openrouter_models()

        # Combine and deduplicate (Google takes priority)
        all_models = google_models + openrouter_models

        # Remove duplicates based on provider+id
        seen = set()
        unique_models = []
        for model in all_models:
            key = (model.provider, model.id)
            if key not in seen:
                seen.add(key)
                unique_models.append(model)

        return unique_models

    def apply_thinking_suffix(self, model_id: str, enabled: bool) -> str:
        """
        Apply or remove :thinking suffix from model ID.

        Args:
            model_id: Base model ID
            enabled: Whether thinking mode is enabled

        Returns:
            Model ID with or without :thinking suffix
        """
        base_id = model_id.replace(":thinking", "")

        if enabled and not model_id.endswith(":thinking"):
            return f"{base_id}:thinking"
        elif not enabled and model_id.endswith(":thinking"):
            return base_id

        return model_id


@lru_cache(maxsize=1)
def get_model_provider_service() -> ModelProviderService:
    """Get cached instance of ModelProviderService."""
    import os
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    return ModelProviderService(openrouter_api_key=openrouter_key)
