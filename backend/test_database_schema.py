#!/usr/bin/env python3
"""Test that the database schema includes the user_settings table."""

import sqlite3
import sys
from pathlib import Path

# Import database service directly without going through __init__
sys.path.insert(0, str(Path(__file__).parent))

from src.services.database import DatabaseService, DEFAULT_DB_PATH


def test_user_settings_table():
    """Verify user_settings table exists with correct schema."""

    # Initialize database (creates tables if they don't exist)
    db_service = DatabaseService()
    db_service.initialize()

    # Connect and check schema
    conn = db_service.connect()
    try:
        # Check if table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='user_settings'"
        )
        result = cursor.fetchone()

        if not result:
            print("✗ user_settings table does not exist")
            return False

        print("✓ user_settings table exists")

        # Check columns
        cursor = conn.execute("PRAGMA table_info(user_settings)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        expected_columns = {
            'user_id': 'TEXT',
            'oracle_model': 'TEXT',
            'oracle_provider': 'TEXT',
            'subagent_model': 'TEXT',
            'subagent_provider': 'TEXT',
            'thinking_enabled': 'INTEGER',
            'created': 'TEXT',
            'updated': 'TEXT'
        }

        for col_name, col_type in expected_columns.items():
            if col_name not in columns:
                print(f"✗ Missing column: {col_name}")
                return False
            if columns[col_name] != col_type:
                print(f"✗ Column {col_name} has wrong type: {columns[col_name]} (expected {col_type})")
                return False

        print("✓ All columns present with correct types")

        # Test insert
        cursor = conn.execute(
            """
            INSERT OR REPLACE INTO user_settings
            (user_id, oracle_model, oracle_provider, subagent_model,
             subagent_provider, thinking_enabled, created, updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "test-user",
                "gemini-2.0-flash-exp",
                "google",
                "deepseek/deepseek-chat",
                "openrouter",
                1,
                "2025-01-01T00:00:00Z",
                "2025-01-01T00:00:00Z"
            )
        )
        conn.commit()

        # Test select
        cursor = conn.execute(
            "SELECT * FROM user_settings WHERE user_id = ?",
            ("test-user",)
        )
        row = cursor.fetchone()

        if not row:
            print("✗ Failed to insert/select test data")
            return False

        print("✓ Insert/select operations work")

        # Clean up test data
        conn.execute("DELETE FROM user_settings WHERE user_id = ?", ("test-user",))
        conn.commit()

        print("✓ Database schema validation complete")
        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    print("Testing database schema for user_settings table...")
    print(f"Database: {DEFAULT_DB_PATH}")
    print()

    success = test_user_settings_table()

    print()
    if success:
        print("✓ All tests passed!")
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        sys.exit(1)
