#!/usr/bin/env python3
"""
Example client for the Model Selection API.

Demonstrates how to interact with the models endpoints.
"""

import asyncio
import httpx
import json
from typing import Optional


class ModelsAPIClient:
    """Client for interacting with the Model Selection API."""

    def __init__(self, base_url: str = "http://localhost:8000", token: Optional[str] = None):
        """
        Initialize the client.

        Args:
            base_url: Base URL of the API
            token: Authentication token (use "local-dev-token" for local development)
        """
        self.base_url = base_url
        self.token = token or "local-dev-token"
        self.headers = {"Authorization": f"Bearer {self.token}"}

    async def get_all_models(self):
        """Get all available models from all providers."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/models",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

    async def get_openrouter_models(self):
        """Get OpenRouter models only."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/models/openrouter",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

    async def get_google_models(self):
        """Get Google AI models only."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/models/google",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

    async def get_settings(self):
        """Get user's current model settings."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/settings/models",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

    async def update_settings(self, **kwargs):
        """
        Update user's model settings.

        Args:
            oracle_model: Oracle model ID
            oracle_provider: Oracle provider ('openrouter' or 'google')
            subagent_model: Subagent model ID
            subagent_provider: Subagent provider
            thinking_enabled: Enable thinking mode
        """
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{self.base_url}/api/settings/models",
                headers=self.headers,
                json=kwargs
            )
            response.raise_for_status()
            return response.json()


async def main():
    """Example usage of the Models API client."""
    client = ModelsAPIClient()

    print("=" * 60)
    print("Model Selection API Client Example")
    print("=" * 60)

    # 1. Get all available models
    print("\n1. Fetching all available models...")
    try:
        all_models = await client.get_all_models()
        print(f"   Found {len(all_models['models'])} models")
        print("\n   Sample models:")
        for model in all_models['models'][:3]:
            print(f"   - {model['name']} ({model['provider']})")
            print(f"     ID: {model['id']}")
            print(f"     Free: {model['is_free']}, Thinking: {model['supports_thinking']}")
    except Exception as e:
        print(f"   Error: {e}")

    # 2. Get OpenRouter models
    print("\n2. Fetching OpenRouter models...")
    try:
        openrouter_models = await client.get_openrouter_models()
        print(f"   Found {len(openrouter_models['models'])} OpenRouter models")
    except Exception as e:
        print(f"   Error: {e}")

    # 3. Get Google models
    print("\n3. Fetching Google models...")
    try:
        google_models = await client.get_google_models()
        print(f"   Found {len(google_models['models'])} Google models")
        for model in google_models['models']:
            print(f"   - {model['name']}")
    except Exception as e:
        print(f"   Error: {e}")

    # 4. Get current settings
    print("\n4. Fetching current user settings...")
    try:
        settings = await client.get_settings()
        print(f"   Oracle: {settings['oracle_model']} ({settings['oracle_provider']})")
        print(f"   Subagent: {settings['subagent_model']} ({settings['subagent_provider']})")
        print(f"   Thinking: {settings['thinking_enabled']}")
    except Exception as e:
        print(f"   Error: {e}")

    # 5. Update settings (example - commented out to avoid changing state)
    print("\n5. Example: Update settings (not executed)")
    print("   To update settings, uncomment the code below:")
    print("""
    updated = await client.update_settings(
        oracle_model="deepseek/deepseek-r1",
        oracle_provider="openrouter",
        thinking_enabled=True
    )
    print(f"   Updated oracle model: {updated['oracle_model']}")
    """)

    # Uncomment to actually update:
    # try:
    #     updated = await client.update_settings(
    #         oracle_model="deepseek/deepseek-r1",
    #         oracle_provider="openrouter",
    #         thinking_enabled=True
    #     )
    #     print(f"   Updated oracle model: {updated['oracle_model']}")
    # except Exception as e:
    #     print(f"   Error: {e}")

    print("\n" + "=" * 60)
    print("Example completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
