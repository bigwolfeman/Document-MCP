# Model Selection API Implementation

## Overview

This implementation adds backend API endpoints for model selection with OpenRouter and Google AI providers. Users can:
- Browse available models from both providers
- Save their model preferences for Oracle and Subagent tasks
- Enable extended thinking mode for supported models

## Architecture

### Database Schema

Added `user_settings` table to store user model preferences:

```sql
CREATE TABLE IF NOT EXISTS user_settings (
    user_id TEXT PRIMARY KEY,
    oracle_model TEXT NOT NULL DEFAULT 'gemini-2.0-flash-exp',
    oracle_provider TEXT NOT NULL DEFAULT 'google',
    subagent_model TEXT NOT NULL DEFAULT 'gemini-2.0-flash-exp',
    subagent_provider TEXT NOT NULL DEFAULT 'google',
    thinking_enabled INTEGER NOT NULL DEFAULT 0,
    created TEXT NOT NULL,
    updated TEXT NOT NULL
)
```

### Pydantic Models (`src/models/settings.py`)

- **ModelProvider**: Enum for provider types (`openrouter`, `google`)
- **ModelSettings**: User's model preferences
- **ModelInfo**: Information about an available model
- **ModelsListResponse**: List of available models
- **ModelSettingsUpdateRequest**: Request to update settings

### Services

#### ModelProviderService (`src/services/model_provider.py`)

Fetches and manages models from multiple providers:

- **`get_openrouter_models()`**: Fetches free models from OpenRouter API
  - Filters for models with `pricing.prompt = "0"`
  - Includes priority models: DeepSeek, Grok, Gemini, Claude, LLaMA
  - Detects thinking support (`:thinking` suffix, "reasoning" in name)

- **`get_google_models()`**: Returns hardcoded Google Gemini models
  - `gemini-2.0-flash-exp` (1M context)
  - `gemini-1.5-pro` (2M context)
  - `gemini-1.5-flash` (1M context)

- **`get_all_models()`**: Combines models from all providers
- **`apply_thinking_suffix()`**: Adds/removes `:thinking` suffix

#### UserSettingsService (`src/services/user_settings.py`)

Manages user settings in database:

- **`get_settings(user_id)`**: Retrieves user settings (returns defaults if not found)
- **`update_settings(user_id, ...)`**: Updates user settings (partial updates supported)

### API Endpoints (`src/api/routes/models.py`)

All endpoints require authentication via Bearer token.

#### GET `/api/models`

Get all available models from all providers.

**Response**: `ModelsListResponse`
```json
{
  "models": [
    {
      "id": "gemini-2.0-flash-exp",
      "name": "Gemini 2.0 Flash (Experimental)",
      "provider": "google",
      "is_free": true,
      "supports_thinking": false,
      "context_length": 1000000,
      "description": "Latest experimental Gemini model..."
    },
    ...
  ]
}
```

#### GET `/api/models/openrouter`

Get free models from OpenRouter API only.

**Response**: `ModelsListResponse` (OpenRouter models only)

#### GET `/api/models/google`

Get Google AI models only.

**Response**: `ModelsListResponse` (Google models only)

#### GET `/api/settings/models`

Get user's current model preferences.

**Response**: `ModelSettings`
```json
{
  "oracle_model": "gemini-2.0-flash-exp",
  "oracle_provider": "google",
  "subagent_model": "deepseek/deepseek-chat",
  "subagent_provider": "openrouter",
  "thinking_enabled": false
}
```

#### PUT `/api/settings/models`

Update user's model preferences (partial updates supported).

**Request**: `ModelSettingsUpdateRequest`
```json
{
  "oracle_model": "deepseek/deepseek-r1",
  "oracle_provider": "openrouter",
  "thinking_enabled": true
}
```

**Response**: `ModelSettings` (updated settings)

## Environment Variables

- **`OPENROUTER_API_KEY`** (optional): OpenRouter API key for authenticated requests
  - Without key: Public endpoint (rate limited)
  - With key: Authenticated endpoint (higher limits)

- **`GOOGLE_API_KEY`**: Google AI API key (already exists in config)

## OpenRouter Integration

### API Reference

- **Base URL**: `https://openrouter.ai/api/v1`
- **Models Endpoint**: `GET /api/v1/models`
- **Documentation**: https://openrouter.ai/docs/api/reference/overview

### Thinking Mode

Models that support extended thinking tokens can use the `:thinking` suffix:

```
deepseek/deepseek-r1:thinking
google/gemini-2.0-flash-thinking-exp:free
```

The `apply_thinking_suffix()` method handles adding/removing this suffix based on user preference.

### Priority Models

The following models are always included (even if not free):

- `deepseek/deepseek-chat`
- `deepseek/deepseek-r1`
- `x-ai/grok-2-1212`
- `google/gemini-2.0-flash-exp:free`
- `google/gemini-2.0-flash-thinking-exp:free`
- `anthropic/claude-3.5-sonnet`
- `meta-llama/llama-3.3-70b-instruct`

## Error Handling

All endpoints include proper error handling:

- **500 Internal Server Error**: Failed to fetch models or update settings
- **401 Unauthorized**: Missing/invalid authentication token
- **Graceful degradation**: If OpenRouter API fails, returns empty list (doesn't crash)

## Testing

### Manual Testing

```bash
# Get all models
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/models

# Get user settings
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/settings/models

# Update settings
curl -X PUT -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"oracle_model": "deepseek/deepseek-r1", "oracle_provider": "openrouter"}' \
  http://localhost:8000/api/settings/models
```

### Integration Test

```bash
cd backend
uv run python test_models_api.py
```

## Future Enhancements

1. **Caching**: Cache OpenRouter models response (currently no caching)
2. **Model validation**: Validate model IDs exist before saving
3. **Cost tracking**: Track API costs per model/user
4. **Model ratings**: User ratings/feedback on model quality
5. **Auto-selection**: Automatically select best model for task type

## Files Created/Modified

### Created
- `/backend/src/models/settings.py` - Pydantic models
- `/backend/src/services/model_provider.py` - Model provider service
- `/backend/src/services/user_settings.py` - User settings service
- `/backend/src/api/routes/models.py` - API endpoints
- `/backend/test_models_api.py` - Syntax validation test

### Modified
- `/backend/src/services/database.py` - Added `user_settings` table
- `/backend/src/api/main.py` - Registered models router

## Usage in Oracle

The vlt-oracle feature will use these settings to:

1. Fetch user's preferred models via `GET /api/settings/models`
2. Use `oracle_model` + `oracle_provider` for main oracle queries
3. Use `subagent_model` + `subagent_provider` for subagent tasks
4. Apply `:thinking` suffix if `thinking_enabled` is true

Example:
```python
from src.services.user_settings import get_user_settings_service

settings_service = get_user_settings_service()
settings = settings_service.get_settings(user_id)

# Use settings.oracle_model and settings.oracle_provider
# for oracle orchestration
```
