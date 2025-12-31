"""Service for managing user settings in the database."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from ..models.settings import ModelSettings, ModelProvider
from .database import DatabaseService

logger = logging.getLogger(__name__)


class UserSettingsService:
    """Service for reading and writing user settings."""

    def __init__(self, db_service: Optional[DatabaseService] = None):
        """Initialize with optional database service."""
        self.db = db_service or DatabaseService()

    def get_settings(self, user_id: str) -> ModelSettings:
        """
        Get user's model settings.

        Args:
            user_id: User identifier

        Returns:
            ModelSettings object (returns defaults if not found)
        """
        conn = self.db.connect()
        try:
            cursor = conn.execute(
                """
                SELECT oracle_model, oracle_provider, subagent_model,
                       subagent_provider, thinking_enabled
                FROM user_settings
                WHERE user_id = ?
                """,
                (user_id,)
            )
            row = cursor.fetchone()

            if row:
                return ModelSettings(
                    oracle_model=row["oracle_model"],
                    oracle_provider=ModelProvider(row["oracle_provider"]),
                    subagent_model=row["subagent_model"],
                    subagent_provider=ModelProvider(row["subagent_provider"]),
                    thinking_enabled=bool(row["thinking_enabled"])
                )
            else:
                # Return defaults for new users
                return ModelSettings()

        except Exception as e:
            logger.error(f"Failed to get settings for user {user_id}: {e}")
            # Return defaults on error
            return ModelSettings()
        finally:
            conn.close()

    def update_settings(
        self,
        user_id: str,
        oracle_model: Optional[str] = None,
        oracle_provider: Optional[ModelProvider] = None,
        subagent_model: Optional[str] = None,
        subagent_provider: Optional[ModelProvider] = None,
        thinking_enabled: Optional[bool] = None
    ) -> ModelSettings:
        """
        Update user's model settings.

        Args:
            user_id: User identifier
            oracle_model: Oracle model ID (optional)
            oracle_provider: Oracle provider (optional)
            subagent_model: Subagent model ID (optional)
            subagent_provider: Subagent provider (optional)
            thinking_enabled: Enable thinking mode (optional)

        Returns:
            Updated ModelSettings object
        """
        conn = self.db.connect()
        try:
            # Get current settings
            current = self.get_settings(user_id)

            # Apply updates (only non-None values)
            updated = ModelSettings(
                oracle_model=oracle_model if oracle_model is not None else current.oracle_model,
                oracle_provider=oracle_provider if oracle_provider is not None else current.oracle_provider,
                subagent_model=subagent_model if subagent_model is not None else current.subagent_model,
                subagent_provider=subagent_provider if subagent_provider is not None else current.subagent_provider,
                thinking_enabled=thinking_enabled if thinking_enabled is not None else current.thinking_enabled
            )

            now = datetime.now(timezone.utc).isoformat()

            # Upsert settings
            with conn:
                conn.execute(
                    """
                    INSERT INTO user_settings (
                        user_id, oracle_model, oracle_provider,
                        subagent_model, subagent_provider, thinking_enabled,
                        created, updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        oracle_model = excluded.oracle_model,
                        oracle_provider = excluded.oracle_provider,
                        subagent_model = excluded.subagent_model,
                        subagent_provider = excluded.subagent_provider,
                        thinking_enabled = excluded.thinking_enabled,
                        updated = excluded.updated
                    """,
                    (
                        user_id,
                        updated.oracle_model,
                        updated.oracle_provider.value,
                        updated.subagent_model,
                        updated.subagent_provider.value,
                        int(updated.thinking_enabled),
                        now,
                        now
                    )
                )

            logger.info(f"Updated settings for user {user_id}")
            return updated

        except Exception as e:
            logger.error(f"Failed to update settings for user {user_id}: {e}")
            raise
        finally:
            conn.close()


def get_user_settings_service() -> UserSettingsService:
    """Get instance of UserSettingsService."""
    return UserSettingsService()
