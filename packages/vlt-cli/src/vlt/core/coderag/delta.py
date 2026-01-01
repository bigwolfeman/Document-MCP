"""Delta-based indexing for CodeRAG.

This module implements User Story 13 (FR-051 through FR-056):
- Queue file changes instead of immediately reindexing
- Batch-commit when delta threshold reached (5 files OR 1000 lines)
- Auto-commit after timeout (5 minutes)
- Support force-commit via `vlt coderag sync --force`
- Just-in-time indexing for uncommitted files matching oracle query
- Expose delta queue status in `vlt coderag status`

Based on tasks T050-T055.
"""

import hashlib
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
from uuid import uuid4

from sqlalchemy import select, delete, func, or_
from sqlalchemy.orm import Session

from vlt.db import engine
from vlt.core.models import (
    IndexDeltaQueue, CodeChunk,
    ChangeType, QueueStatus
)

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration - Thresholds for batch commits (FR-052, FR-053)
# ============================================================================

class DeltaConfig:
    """Configuration for delta-based indexing."""

    # Threshold: batch commit when 5 files queued
    FILES_THRESHOLD = 5

    # Threshold: batch commit when 1000 lines changed
    LINES_THRESHOLD = 1000

    # Timeout: auto-commit after 5 minutes of last change
    TIMEOUT_MINUTES = 5

    # Priority levels for queue
    PRIORITY_NORMAL = 0
    PRIORITY_HIGH = 1
    PRIORITY_CRITICAL = 2


# ============================================================================
# T050: File Change Detection (hash comparison)
# ============================================================================

def calculate_file_hash(file_path: Path) -> str:
    """Calculate MD5 hash of file content for change detection.

    Args:
        file_path: Path to the file

    Returns:
        32-character hex MD5 hash

    Raises:
        IOError: If file cannot be read
    """
    try:
        with open(file_path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception as e:
        logger.error(f"Error calculating hash for {file_path}: {e}")
        raise


def detect_file_changes(
    file_path: Path,
    project_id: str,
    project_root: Path
) -> Optional[Tuple[ChangeType, str, Optional[str]]]:
    """Detect if a file has changed since last index.

    Compares current file hash with stored hash in database.

    Args:
        file_path: Absolute path to the file
        project_id: Project identifier
        project_root: Root directory of the project

    Returns:
        Tuple of (change_type, old_hash, new_hash) if changed, None if unchanged

    Change types:
        - ADDED: New file not in index
        - MODIFIED: Existing file with different hash
        - DELETED: File in index but missing from filesystem
    """
    try:
        # Get relative path for database lookup
        relative_path = str(file_path.relative_to(project_root))

        with Session(engine) as session:
            # Check if file exists in index
            existing_chunk = session.scalar(
                select(CodeChunk)
                .where(
                    CodeChunk.project_id == project_id,
                    CodeChunk.file_path == relative_path
                )
                .limit(1)
            )

            # File exists - check if it's been modified
            if file_path.exists():
                current_hash = calculate_file_hash(file_path)

                if existing_chunk is None:
                    # New file
                    return (ChangeType.ADDED, None, current_hash)
                elif existing_chunk.file_hash != current_hash:
                    # Modified file
                    return (ChangeType.MODIFIED, existing_chunk.file_hash, current_hash)
                else:
                    # Unchanged
                    return None
            else:
                # File deleted
                if existing_chunk:
                    return (ChangeType.DELETED, existing_chunk.file_hash, None)
                else:
                    # File never existed in index
                    return None

    except Exception as e:
        logger.error(f"Error detecting changes for {file_path}: {e}")
        return None


def count_lines_changed(file_path: Path, old_hash: Optional[str], new_hash: Optional[str]) -> int:
    """Estimate number of lines changed in a file.

    For simplicity, this estimates based on file size rather than doing a full diff.
    A more accurate implementation could use difflib or git diff.

    Args:
        file_path: Path to the file
        old_hash: Previous file hash (None if added)
        new_hash: New file hash (None if deleted)

    Returns:
        Estimated number of lines changed
    """
    try:
        if new_hash is None:
            # Deleted - count all lines as changed
            # Can't read file anymore, estimate from database
            return 100  # Conservative estimate

        if old_hash is None:
            # Added - count all lines
            with open(file_path, 'r', encoding='utf-8') as f:
                return sum(1 for _ in f)

        # Modified - for now, estimate as 1/4 of file size
        # (most edits are small changes)
        with open(file_path, 'r', encoding='utf-8') as f:
            total_lines = sum(1 for _ in f)
            return max(1, total_lines // 4)

    except Exception as e:
        logger.warning(f"Error counting lines for {file_path}: {e}")
        return 50  # Default estimate


# ============================================================================
# T051: Delta Queue Manager
# ============================================================================

class DeltaQueueManager:
    """Manager for delta queue operations.

    Handles:
    - Adding files to queue
    - Checking thresholds
    - Batch commits
    - Queue status queries
    """

    def __init__(self, project_id: str, config: Optional[DeltaConfig] = None):
        """Initialize delta queue manager.

        Args:
            project_id: Project identifier
            config: Optional configuration (uses defaults if None)
        """
        self.project_id = project_id
        self.config = config or DeltaConfig()

    def queue_file_change(
        self,
        file_path: Path,
        project_root: Path,
        change_type: ChangeType,
        old_hash: Optional[str],
        new_hash: Optional[str],
        priority: int = DeltaConfig.PRIORITY_NORMAL
    ) -> bool:
        """Add a file change to the delta queue.

        Args:
            file_path: Absolute path to the changed file
            project_root: Root directory of the project
            change_type: Type of change (ADDED, MODIFIED, DELETED)
            old_hash: Previous file hash (None if added)
            new_hash: New file hash (None if deleted)
            priority: Priority level (0=normal, 1=high, 2=critical)

        Returns:
            True if queued successfully, False otherwise
        """
        try:
            relative_path = str(file_path.relative_to(project_root))
            lines_changed = count_lines_changed(file_path, old_hash, new_hash)

            with Session(engine) as session:
                # Check if file is already queued
                existing = session.scalar(
                    select(IndexDeltaQueue)
                    .where(
                        IndexDeltaQueue.project_id == self.project_id,
                        IndexDeltaQueue.file_path == relative_path,
                        IndexDeltaQueue.status == QueueStatus.PENDING
                    )
                )

                if existing:
                    # Update existing queue entry
                    existing.change_type = change_type
                    existing.old_hash = old_hash
                    existing.new_hash = new_hash
                    existing.lines_changed = lines_changed
                    existing.detected_at = datetime.now(timezone.utc)
                    existing.priority = max(existing.priority, priority)  # Upgrade priority
                    logger.info(f"Updated queue entry for {relative_path}")
                else:
                    # Create new queue entry
                    queue_entry = IndexDeltaQueue(
                        id=str(uuid4()),
                        project_id=self.project_id,
                        file_path=relative_path,
                        change_type=change_type,
                        old_hash=old_hash,
                        new_hash=new_hash,
                        lines_changed=lines_changed,
                        detected_at=datetime.now(timezone.utc),
                        queued_at=datetime.now(timezone.utc),
                        priority=priority,
                        status=QueueStatus.PENDING,
                    )
                    session.add(queue_entry)
                    logger.info(f"Queued {change_type.value} for {relative_path} (+{lines_changed} lines)")

                session.commit()
                return True

        except Exception as e:
            logger.error(f"Error queuing file change: {e}")
            return False

    def check_thresholds(self) -> bool:
        """Check if delta queue has reached commit thresholds.

        Returns:
            True if any threshold is exceeded, False otherwise

        Thresholds (FR-052):
            - FILES_THRESHOLD: 5 files queued
            - LINES_THRESHOLD: 1000 lines changed

        Timeout (FR-053):
            - TIMEOUT_MINUTES: 5 minutes since last change
        """
        try:
            with Session(engine) as session:
                # Get pending queue entries
                pending = session.scalars(
                    select(IndexDeltaQueue)
                    .where(
                        IndexDeltaQueue.project_id == self.project_id,
                        IndexDeltaQueue.status == QueueStatus.PENDING
                    )
                ).all()

                if not pending:
                    return False

                # Check files threshold
                if len(pending) >= self.config.FILES_THRESHOLD:
                    logger.info(f"Files threshold reached: {len(pending)}/{self.config.FILES_THRESHOLD}")
                    return True

                # Check lines threshold
                total_lines = sum(entry.lines_changed or 0 for entry in pending)
                if total_lines >= self.config.LINES_THRESHOLD:
                    logger.info(f"Lines threshold reached: {total_lines}/{self.config.LINES_THRESHOLD}")
                    return True

                # Check timeout threshold
                oldest_entry = min(pending, key=lambda e: e.detected_at)
                age = datetime.now(timezone.utc) - oldest_entry.detected_at
                timeout_threshold = timedelta(minutes=self.config.TIMEOUT_MINUTES)

                if age >= timeout_threshold:
                    logger.info(f"Timeout threshold reached: {age.total_seconds():.0f}s (threshold: {timeout_threshold.total_seconds():.0f}s)")
                    return True

                return False

        except Exception as e:
            logger.error(f"Error checking thresholds: {e}")
            return False

    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status with detailed statistics.

        Returns:
            Dictionary with queue statistics:
                - queued_files: Number of files pending
                - queued_entries: List of pending file details
                - total_lines: Total lines changed
                - oldest_age_seconds: Age of oldest entry in seconds
                - should_commit: Whether thresholds are exceeded
        """
        try:
            with Session(engine) as session:
                # Get pending entries
                pending = session.scalars(
                    select(IndexDeltaQueue)
                    .where(
                        IndexDeltaQueue.project_id == self.project_id,
                        IndexDeltaQueue.status == QueueStatus.PENDING
                    )
                    .order_by(IndexDeltaQueue.priority.desc(), IndexDeltaQueue.detected_at.asc())
                ).all()

                if not pending:
                    return {
                        "queued_files": 0,
                        "queued_entries": [],
                        "total_lines": 0,
                        "oldest_age_seconds": 0,
                        "should_commit": False,
                        "files_threshold": self.config.FILES_THRESHOLD,
                        "lines_threshold": self.config.LINES_THRESHOLD,
                        "timeout_seconds": self.config.TIMEOUT_MINUTES * 60,
                    }

                # Build entry details
                entries = []
                for entry in pending:
                    age = datetime.now(timezone.utc) - entry.detected_at
                    entries.append({
                        "file_path": entry.file_path,
                        "change_type": entry.change_type.value,
                        "lines_changed": entry.lines_changed,
                        "age_seconds": int(age.total_seconds()),
                        "priority": entry.priority,
                    })

                total_lines = sum(e["lines_changed"] or 0 for e in entries)
                oldest_age = max(e["age_seconds"] for e in entries)

                return {
                    "queued_files": len(entries),
                    "queued_entries": entries,
                    "total_lines": total_lines,
                    "oldest_age_seconds": oldest_age,
                    "should_commit": self.check_thresholds(),
                    "files_threshold": self.config.FILES_THRESHOLD,
                    "lines_threshold": self.config.LINES_THRESHOLD,
                    "timeout_seconds": self.config.TIMEOUT_MINUTES * 60,
                }

        except Exception as e:
            logger.error(f"Error getting queue status: {e}")
            return {
                "queued_files": 0,
                "queued_entries": [],
                "total_lines": 0,
                "oldest_age_seconds": 0,
                "should_commit": False,
                "error": str(e)
            }

    def get_pending_files(self) -> List[str]:
        """Get list of pending file paths in queue.

        Returns:
            List of relative file paths
        """
        try:
            with Session(engine) as session:
                pending = session.scalars(
                    select(IndexDeltaQueue.file_path)
                    .where(
                        IndexDeltaQueue.project_id == self.project_id,
                        IndexDeltaQueue.status == QueueStatus.PENDING
                    )
                ).all()

                return list(pending)

        except Exception as e:
            logger.error(f"Error getting pending files: {e}")
            return []

    def mark_as_indexed(self, file_paths: List[str]) -> int:
        """Mark files as indexed (remove from queue).

        Args:
            file_paths: List of relative file paths that were indexed

        Returns:
            Number of queue entries removed
        """
        try:
            with Session(engine) as session:
                result = session.execute(
                    delete(IndexDeltaQueue)
                    .where(
                        IndexDeltaQueue.project_id == self.project_id,
                        IndexDeltaQueue.file_path.in_(file_paths),
                        IndexDeltaQueue.status == QueueStatus.PENDING
                    )
                )
                session.commit()

                removed = result.rowcount
                logger.info(f"Removed {removed} entries from delta queue")
                return removed

        except Exception as e:
            logger.error(f"Error marking files as indexed: {e}")
            return 0

    def clear_queue(self) -> int:
        """Clear all pending entries from queue.

        Returns:
            Number of entries cleared
        """
        try:
            with Session(engine) as session:
                result = session.execute(
                    delete(IndexDeltaQueue)
                    .where(
                        IndexDeltaQueue.project_id == self.project_id,
                        IndexDeltaQueue.status == QueueStatus.PENDING
                    )
                )
                session.commit()

                cleared = result.rowcount
                logger.info(f"Cleared {cleared} entries from delta queue")
                return cleared

        except Exception as e:
            logger.error(f"Error clearing queue: {e}")
            return 0


# ============================================================================
# T053: Just-in-Time Indexing
# ============================================================================

def get_files_matching_query(
    query: str,
    project_id: str,
    pending_files: List[str]
) -> List[str]:
    """Get pending files that might be relevant to a query.

    This uses simple heuristics:
    - If query mentions a file path, include that file
    - If query mentions a symbol/function/class name, check file names

    A more sophisticated version could use LSP or symbol tables.

    Args:
        query: Natural language query from user
        project_id: Project identifier
        pending_files: List of relative file paths in delta queue

    Returns:
        List of file paths that should be indexed immediately
    """
    matching = []

    # Extract potential file paths and symbols from query
    # Simple heuristic: look for words with extensions or capitalized names
    words = query.split()

    for file_path in pending_files:
        file_name = Path(file_path).name
        file_stem = Path(file_path).stem

        # Check if file path is mentioned
        if file_path in query or file_name in query:
            matching.append(file_path)
            continue

        # Check if file stem matches any word in query
        for word in words:
            word_clean = word.strip('.,!?()[]{}').lower()
            if word_clean == file_stem.lower():
                matching.append(file_path)
                break

    if matching:
        logger.info(f"Just-in-time indexing triggered for {len(matching)} files matching query")

    return matching


# ============================================================================
# Utility Functions
# ============================================================================

def scan_directory_for_changes(
    project_root: Path,
    project_id: str,
    include_patterns: List[str],
    exclude_patterns: List[str]
) -> List[Tuple[Path, ChangeType, Optional[str], Optional[str]]]:
    """Scan directory for changed files.

    Args:
        project_root: Root directory of the project
        project_id: Project identifier
        include_patterns: List of glob patterns to include
        exclude_patterns: List of glob patterns to exclude

    Returns:
        List of (file_path, change_type, old_hash, new_hash) tuples
    """
    import fnmatch

    changes = []

    # Collect all files matching include patterns
    for pattern in include_patterns:
        for file_path in project_root.glob(pattern):
            if not file_path.is_file():
                continue

            # Check exclude patterns
            relative_path = str(file_path.relative_to(project_root))
            excluded = False
            for exclude_pattern in exclude_patterns:
                if fnmatch.fnmatch(relative_path, exclude_pattern.replace("**", "*")):
                    excluded = True
                    break

            if excluded:
                continue

            # Detect changes
            change = detect_file_changes(file_path, project_id, project_root)
            if change:
                change_type, old_hash, new_hash = change
                changes.append((file_path, change_type, old_hash, new_hash))

    return changes
