# Model Selection API - Complete Implementation

## Overview

This implementation provides a complete backend API for managing AI model selection with support for:
- **OpenRouter**: Access to free models including DeepSeek, Grok, and more
- **Google AI**: Gemini models (2.0 Flash, 1.5 Pro, 1.5 Flash)
- **User Preferences**: Save and retrieve per-user model settings
- **Thinking Mode**: Support for extended reasoning tokens (`:thinking` suffix)

## Quick Start

### 1. Start the Backend

```bash
cd backend
uv run uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Test the API

Using the example client:

```bash
cd backend
python example_models_client.py
```

Or with curl:

```bash
# Get all models
curl -H "Authorization: Bearer local-dev-token" \
  http://localhost:8000/api/models | jq

# Get user settings
curl -H "Authorization: Bearer local-dev-token" \
  http://localhost:8000/api/settings/models | jq

# Update settings
curl -X PUT -H "Authorization: Bearer local-dev-token" \
  -H "Content-Type: application/json" \
  -d '{"oracle_model": "deepseek/deepseek-r1", "oracle_provider": "openrouter"}' \
  http://localhost:8000/api/settings/models | jq
```

### 3. Verify Database Schema

```bash
cd backend
python test_database_schema.py
```

## API Endpoints

### GET /api/models
Get all available models from all providers.

**Response:**
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
    }
  ]
}
```

### GET /api/models/openrouter
Get free models from OpenRouter only.

### GET /api/models/google
Get Google AI models only.

### GET /api/settings/models
Get user's current model preferences.

**Response:**
```json
{
  "oracle_model": "gemini-2.0-flash-exp",
  "oracle_provider": "google",
  "subagent_model": "deepseek/deepseek-chat",
  "subagent_provider": "openrouter",
  "thinking_enabled": false
}
```

### PUT /api/settings/models
Update user's model preferences (partial updates supported).

**Request:**
```json
{
  "oracle_model": "deepseek/deepseek-r1",
  "oracle_provider": "openrouter",
  "thinking_enabled": true
}
```

## Architecture

### Database Schema

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

### Code Structure

```
backend/src/
├── models/
│   └── settings.py           # Pydantic models for API
├── services/
│   ├── model_provider.py     # Fetch models from providers
│   ├── user_settings.py      # Manage user settings in DB
│   └── database.py           # Database schema (modified)
└── api/
    └── routes/
        └── models.py         # API endpoints
```

### Service Layer

#### ModelProviderService

Fetches models from multiple providers:

```python
from src.services.model_provider import get_model_provider_service

provider_service = get_model_provider_service()

# Get all models
models = await provider_service.get_all_models()

# Get OpenRouter models only
openrouter_models = await provider_service.get_openrouter_models()

# Get Google models only
google_models = provider_service.get_google_models()

# Apply thinking suffix
model_with_thinking = provider_service.apply_thinking_suffix(
    "deepseek/deepseek-r1",
    enabled=True
)  # Returns: "deepseek/deepseek-r1:thinking"
```

#### UserSettingsService

Manages user preferences:

```python
from src.services.user_settings import get_user_settings_service

settings_service = get_user_settings_service()

# Get user's settings
settings = settings_service.get_settings("user-123")

# Update settings (partial updates)
updated = settings_service.update_settings(
    user_id="user-123",
    oracle_model="deepseek/deepseek-r1",
    oracle_provider=ModelProvider.OPENROUTER,
    thinking_enabled=True
)
```

## OpenRouter Integration

### Free Models

The API fetches models from `https://openrouter.ai/api/v1/models` and filters for:
- Models with `pricing.prompt = "0"`
- Priority models (always included)

### Priority Models

These models are always included, even if not free:
- `deepseek/deepseek-chat`
- `deepseek/deepseek-r1`
- `x-ai/grok-2-1212`
- `google/gemini-2.0-flash-exp:free`
- `google/gemini-2.0-flash-thinking-exp:free`
- `anthropic/claude-3.5-sonnet`
- `meta-llama/llama-3.3-70b-instruct`

### Thinking Mode

Models that support extended reasoning can use the `:thinking` suffix:

```python
# Enable thinking mode
settings_service.update_settings(
    user_id="user-123",
    oracle_model="deepseek/deepseek-r1",
    thinking_enabled=True
)

# The model will be used as "deepseek/deepseek-r1:thinking"
```

Detection logic:
- Model ID contains `:thinking`
- Model name contains "reasoning"
- Model ID contains "r1" or "o1"

## Configuration

### Environment Variables

```bash
# Optional: OpenRouter API key for authenticated access
OPENROUTER_API_KEY=your-key-here

# Already exists: Google AI API key
GOOGLE_API_KEY=your-key-here
```

Without `OPENROUTER_API_KEY`, the API uses the public endpoint (rate limited).

## Testing

### Syntax Validation

```bash
cd backend
python test_models_api.py
```

### Database Schema

```bash
cd backend
python test_database_schema.py
```

### Example Client

```bash
cd backend
python example_models_client.py
```

## Integration with vlt-oracle

The oracle orchestrator can use these settings:

```python
from src.services.user_settings import get_user_settings_service
from src.services.model_provider import get_model_provider_service

# Get user's preferences
settings_service = get_user_settings_service()
provider_service = get_model_provider_service()

settings = settings_service.get_settings(user_id)

# Configure oracle model
if settings.oracle_provider == "google":
    model = settings.oracle_model
    # Use Google AI API
else:
    model = settings.oracle_model
    if settings.thinking_enabled:
        model = provider_service.apply_thinking_suffix(model, True)
    # Use OpenRouter API

# Configure subagent model
if settings.subagent_provider == "google":
    subagent_model = settings.subagent_model
else:
    subagent_model = settings.subagent_model
    if settings.thinking_enabled:
        subagent_model = provider_service.apply_thinking_suffix(subagent_model, True)
```

## Error Handling

All endpoints include proper error handling:

- **401 Unauthorized**: Missing or invalid auth token
- **500 Internal Server Error**: Failed to fetch models or update settings
- **Graceful degradation**: If OpenRouter API fails, returns empty list

## Security

- All endpoints require authentication via Bearer token
- User settings isolated by user_id
- Input validation via Pydantic models
- No sensitive data in responses

## Performance

- Async HTTP requests to OpenRouter (non-blocking)
- Simple database lookups (indexed by user_id)
- Lightweight JSON responses
- No caching (future enhancement)

## Files Reference

### Created Files

- `src/models/settings.py` - Pydantic models
- `src/services/model_provider.py` - Model fetching service
- `src/services/user_settings.py` - Settings persistence
- `src/api/routes/models.py` - API endpoints
- `test_models_api.py` - Syntax validation
- `test_database_schema.py` - DB schema test
- `example_models_client.py` - Usage example
- `MODEL_SELECTION_API.md` - Full documentation
- `IMPLEMENTATION_SUMMARY.md` - Implementation summary

### Modified Files

- `src/services/database.py` - Added user_settings table
- `src/api/main.py` - Registered models router
- `src/api/routes/__init__.py` - Added models import

## Next Steps

1. **Frontend UI**: Create React components for model selection
2. **Oracle Integration**: Use settings in vlt-oracle orchestrator
3. **Cost Tracking**: Track API usage per model
4. **Model Validation**: Verify model IDs before saving
5. **Response Caching**: Cache OpenRouter API responses
6. **Model Health**: Track model availability/errors
7. **Usage Analytics**: Track which models are most popular

## Support

For issues or questions:
1. Check `MODEL_SELECTION_API.md` for detailed API documentation
2. Run `test_database_schema.py` to verify database setup
3. Use `example_models_client.py` to test connectivity
4. Check backend logs for error details

## License

Part of the Vlt-Bridge project.
