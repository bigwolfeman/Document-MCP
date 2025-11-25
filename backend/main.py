"""Entry point for running the FastAPI application."""

import os
import uvicorn

if __name__ == "__main__":
    # Read port from environment variable, default to 8001 for FastAPI server
    # (matches frontend proxy config and development scripts)
    # Can be overridden: PORT=8000 python main.py
    # Docker sets PORT=7860 via CMD
    # port = int(os.getenv("PORT", "8001"))

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
