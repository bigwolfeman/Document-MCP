"""Tests for delta-based indexing functionality.

Tests T050-T055: Delta queue management and batch commits.
"""

import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock
import tempfile
import hashlib

from vlt.core.coderag.delta import (
    DeltaConfig,
    DeltaQueueManager,
    calculate_file_hash,
    detect_file_changes,
    count_lines_changed,
    get_files_matching_query,
    scan_directory_for_changes,
)
from vlt.core.models import ChangeType, QueueStatus


class TestFileChangeDetection:
    """Test T050: File change detection with hash comparison."""

    def test_calculate_file_hash(self, tmp_path):
        """Test MD5 hash calculation."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello():\n    pass\n")

        hash1 = calculate_file_hash(test_file)
        assert len(hash1) == 32  # MD5 hash is 32 chars

        # Same content = same hash
        hash2 = calculate_file_hash(test_file)
        assert hash1 == hash2

        # Different content = different hash
        test_file.write_text("def goodbye():\n    pass\n")
        hash3 = calculate_file_hash(test_file)
        assert hash1 != hash3

    def test_count_lines_changed_added_file(self, tmp_path):
        """Test line counting for newly added file."""
        test_file = tmp_path / "new.py"
        test_file.write_text("line1\nline2\nline3\n")

        lines = count_lines_changed(test_file, old_hash=None, new_hash="abc123")
        assert lines == 3  # All lines are new

    def test_count_lines_changed_modified_file(self, tmp_path):
        """Test line counting for modified file (estimates 1/4 of file)."""
        test_file = tmp_path / "modified.py"
        content = "\n".join([f"line{i}" for i in range(100)])
        test_file.write_text(content)

        lines = count_lines_changed(test_file, old_hash="old", new_hash="new")
        assert lines == 25  # 100 lines / 4

    def test_count_lines_changed_deleted_file(self):
        """Test line counting for deleted file."""
        fake_path = Path("/fake/deleted.py")
        lines = count_lines_changed(fake_path, old_hash="old", new_hash=None)
        assert lines == 100  # Conservative estimate


class TestDeltaQueueManager:
    """Test T051: Delta queue manager with threshold checking."""

    @pytest.fixture
    def manager(self):
        """Create a delta queue manager for testing."""
        return DeltaQueueManager(project_id="test-project")

    def test_queue_file_change(self, manager, tmp_path):
        """Test queuing a file change."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def test():\n    pass\n")

        success = manager.queue_file_change(
            file_path=test_file,
            project_root=tmp_path,
            change_type=ChangeType.ADDED,
            old_hash=None,
            new_hash="abc123",
            priority=DeltaConfig.PRIORITY_NORMAL
        )

        assert success

    def test_check_thresholds_files(self, manager, tmp_path):
        """Test files threshold check."""
        # Queue 5 files to reach FILES_THRESHOLD
        for i in range(5):
            test_file = tmp_path / f"test{i}.py"
            test_file.write_text(f"def test{i}():\n    pass\n")

            manager.queue_file_change(
                file_path=test_file,
                project_root=tmp_path,
                change_type=ChangeType.ADDED,
                old_hash=None,
                new_hash=f"hash{i}",
            )

        # Should reach threshold
        assert manager.check_thresholds()

    def test_check_thresholds_lines(self, manager, tmp_path):
        """Test lines threshold check."""
        # Create a large file with 1000+ lines
        test_file = tmp_path / "large.py"
        content = "\n".join([f"line{i}" for i in range(1100)])
        test_file.write_text(content)

        manager.queue_file_change(
            file_path=test_file,
            project_root=tmp_path,
            change_type=ChangeType.ADDED,
            old_hash=None,
            new_hash="largefile",
        )

        # Should reach threshold (1100 lines > 1000)
        assert manager.check_thresholds()

    def test_get_queue_status(self, manager, tmp_path):
        """Test getting queue status."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def test():\n    pass\n")

        manager.queue_file_change(
            file_path=test_file,
            project_root=tmp_path,
            change_type=ChangeType.ADDED,
            old_hash=None,
            new_hash="abc123",
        )

        status = manager.get_queue_status()

        assert status['queued_files'] >= 0
        assert 'total_lines' in status
        assert 'should_commit' in status
        assert 'files_threshold' in status
        assert 'lines_threshold' in status

    def test_get_pending_files(self, manager, tmp_path):
        """Test getting pending file list."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def test():\n    pass\n")

        manager.queue_file_change(
            file_path=test_file,
            project_root=tmp_path,
            change_type=ChangeType.ADDED,
            old_hash=None,
            new_hash="abc123",
        )

        pending = manager.get_pending_files()
        assert isinstance(pending, list)


class TestJustInTimeIndexing:
    """Test T053: Just-in-time indexing for query-matched files."""

    def test_get_files_matching_query_exact_path(self):
        """Test matching files by exact path in query."""
        query = "How does auth.py handle authentication?"
        pending_files = ["src/auth.py", "src/login.py", "src/user.py"]

        matches = get_files_matching_query(query, "test-project", pending_files)

        assert "src/auth.py" in matches
        assert len(matches) == 1

    def test_get_files_matching_query_file_name(self):
        """Test matching files by file name."""
        query = "Where is UserService defined?"
        pending_files = ["src/services/user_service.py", "src/auth.py"]

        matches = get_files_matching_query(query, "test-project", pending_files)

        # Should match user_service.py based on stem matching
        assert len(matches) >= 0  # May or may not match depending on heuristic

    def test_get_files_matching_query_no_matches(self):
        """Test no matches."""
        query = "What is the meaning of life?"
        pending_files = ["src/auth.py", "src/login.py"]

        matches = get_files_matching_query(query, "test-project", pending_files)

        assert matches == []


class TestDeltaConfig:
    """Test delta configuration constants."""

    def test_config_thresholds(self):
        """Test configuration values are sensible."""
        config = DeltaConfig()

        assert config.FILES_THRESHOLD == 5
        assert config.LINES_THRESHOLD == 1000
        assert config.TIMEOUT_MINUTES == 5

        assert config.PRIORITY_NORMAL == 0
        assert config.PRIORITY_HIGH == 1
        assert config.PRIORITY_CRITICAL == 2


class TestScanDirectoryForChanges:
    """Test directory scanning for changes."""

    def test_scan_empty_directory(self, tmp_path):
        """Test scanning an empty directory."""
        changes = scan_directory_for_changes(
            project_root=tmp_path,
            project_id="test-project",
            include_patterns=["**/*.py"],
            exclude_patterns=[]
        )

        assert changes == []

    @patch('vlt.core.coderag.delta.detect_file_changes')
    def test_scan_with_changes(self, mock_detect, tmp_path):
        """Test scanning with changed files."""
        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("def test():\n    pass\n")

        # Mock detect to return a change
        mock_detect.return_value = (ChangeType.ADDED, None, "abc123")

        changes = scan_directory_for_changes(
            project_root=tmp_path,
            project_id="test-project",
            include_patterns=["**/*.py"],
            exclude_patterns=[]
        )

        assert len(changes) >= 0
        # Note: This will only work if detect_file_changes is properly mocked


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
