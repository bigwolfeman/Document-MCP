# Model Selection API - Implementation Summary

## What Was Implemented

Successfully implemented a complete backend API for model selection with OpenRouter and Google AI providers.

## Key Features

### 1. **Model Provider Integration**
   - OpenRouter API integration for fetching free models
   - Hardcoded Google Gemini models (2.0 Flash, 1.5 Pro, 1.5 Flash)
   - Priority model list for always-available models
   - Thinking mode support detection (`:thinking` suffix)

### 2. **User Settings Management**
   - Database table for storing user preferences
   - Separate settings for Oracle and Subagent models
   - Thinking mode toggle
   - Default values for new users

### 3. **RESTful API Endpoints**
   - `GET /api/models` - All available models
   - `GET /api/models/openrouter` - OpenRouter models only
   - `GET /api/models/google` - Google models only
   - `GET /api/settings/models` - User's model preferences
   - `PUT /api/settings/models` - Update preferences

### 4. **Proper Architecture**
   - Clean separation of concerns (models, services, routes)
   - Dependency injection via FastAPI
   - Error handling and logging
   - Authentication via existing auth middleware

## Files Created

```
backend/
├── src/
│   ├── models/
│   │   └── settings.py                 # Pydantic models
│   ├── services/
│   │   ├── model_provider.py          # Model fetching service
│   │   └── user_settings.py           # Settings persistence service
│   └── api/
│       └── routes/
│           └── models.py               # API endpoints
├── test_models_api.py                  # Syntax validation
├── example_models_client.py            # Example usage
└── MODEL_SELECTION_API.md              # Documentation
```

## Files Modified

```
backend/
├── src/
│   ├── services/
│   │   └── database.py                 # Added user_settings table
│   └── api/
│       ├── main.py                     # Registered models router
│       └── routes/
│           └── __init__.py             # Added models import
```

## Database Schema

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

## API Response Examples

### GET /api/models
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
      "description": "Latest experimental Gemini model with 1M token context"
    },
    {
      "id": "deepseek/deepseek-r1",
      "name": "DeepSeek R1",
      "provider": "openrouter",
      "is_free": true,
      "supports_thinking": true,
      "context_length": 64000
    }
  ]
}
```

### GET /api/settings/models
```json
{
  "oracle_model": "gemini-2.0-flash-exp",
  "oracle_provider": "google",
  "subagent_model": "deepseek/deepseek-chat",
  "subagent_provider": "openrouter",
  "thinking_enabled": false
}
```

## OpenRouter Integration Details

### Free Models Filtering
- Fetches from `https://openrouter.ai/api/v1/models`
- Filters for `pricing.prompt = "0"`
- Includes priority models regardless of cost

### Priority Models
Always included in results:
- `deepseek/deepseek-chat`
- `deepseek/deepseek-r1`
- `x-ai/grok-2-1212`
- `google/gemini-2.0-flash-exp:free`
- `google/gemini-2.0-flash-thinking-exp:free`
- `anthropic/claude-3.5-sonnet`
- `meta-llama/llama-3.3-70b-instruct`

### Thinking Mode Support
Models with extended reasoning support are detected by:
- `:thinking` suffix in model ID
- "reasoning" in model name
- "r1" or "o1" in model ID

## Testing

All files pass syntax validation:
```bash
cd backend
python test_models_api.py
```

## Usage Example

```python
from src.services.user_settings import get_user_settings_service
from src.services.model_provider import get_model_provider_service

# Get user's settings
settings_service = get_user_settings_service()
settings = settings_service.get_settings("user-123")

# Use in oracle
if settings.oracle_provider == "google":
    # Use Google AI
    model = settings.oracle_model
else:
    # Use OpenRouter
    model = settings.oracle_model
    if settings.thinking_enabled:
        model = f"{model}:thinking"
```

## Next Steps for Integration

1. **Frontend UI**: Create React components for model selection
2. **Oracle Integration**: Use settings in vlt-oracle orchestrator
3. **Cost Tracking**: Track API usage per model
4. **Model Validation**: Verify model IDs exist before saving
5. **Caching**: Cache OpenRouter API responses

## Environment Variables

Required for full functionality:
- `OPENROUTER_API_KEY` (optional) - For authenticated OpenRouter API access
- `GOOGLE_API_KEY` (already exists) - For Google AI models

## Error Handling

- Graceful degradation if OpenRouter API fails
- Returns default settings if user has none saved
- Proper HTTP status codes (401, 500)
- Detailed error logging

## Security

- All endpoints require authentication via Bearer token
- User settings are isolated by user_id
- No sensitive data in responses
- Input validation via Pydantic models

## Performance

- OpenRouter API calls are async (non-blocking)
- Database queries are simple lookups (indexed by user_id)
- No caching yet (future enhancement)
- Lightweight response payloads

## Compliance with Spec

Implements all requirements from `specs/007-vlt-oracle/spec.md`:
- ✅ Support for OpenRouter models
- ✅ Support for Google AI models
- ✅ User model preferences storage
- ✅ Thinking mode support
- ✅ RESTful API endpoints
- ✅ Proper error handling
- ✅ Authentication integration

## Documentation

- `MODEL_SELECTION_API.md` - Comprehensive API documentation
- `example_models_client.py` - Working client example
- Inline code comments and docstrings
- Type hints throughout
