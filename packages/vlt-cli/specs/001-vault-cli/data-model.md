# Data Model: Vault CLI

## Entities

### Project
Logical grouping of work.
- `id` (PK): String (slug) - e.g., "crypto-bot"
- `name`: String
- `created_at`: Datetime
- `description`: Text

### Thread
A stream of consciousness within a project.
- `id` (PK): String (slug) - e.g., "optim-strategy"
- `project_id` (FK): String -> Project.id
- `created_at`: Datetime
- `status`: Enum (Active, Archived, Blocked)

### Node
An immutable thought unit.
- `id` (PK): String (UUID or Hash)
- `thread_id` (FK): String -> Thread.id
- `sequence_id`: Integer (Auto-increment per thread for ordering)
- `content`: Text (The thought)
- `author`: String (Agent or User)
- `timestamp`: Datetime
- `embedding`: BLOB (Serialized float32 array) - Nullable (until processed)
- `prev_node_id` (FK): String -> Node.id (Self-ref, Null for first node)

### State
The summarized context of a thread or project.
- `id` (PK): String (UUID)
- `target_id` (FK): String (Thread.id or Project.id)
- `target_type`: Enum (Thread, Project)
- `summary`: Text (Markdown)
- `head_node_id` (FK): String -> Node.id (The last node included in this summary)
- `updated_at`: Datetime
- `meta`: JSON (Additional structured data like "Active Constraints")

## Database Schema (SQLAlchemy Style)

```python
class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(primary_key=True)
    description: Mapped[str]

class Thread(Base):
    __tablename__ = "threads"
    id: Mapped[str] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    
class Node(Base):
    __tablename__ = "nodes"
    id: Mapped[str] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id"))
    content: Mapped[str]
    embedding: Mapped[Optional[bytes]] # Stored as bytes
    
class State(Base):
    __tablename__ = "states"
    id: Mapped[str] = mapped_column(primary_key=True)
    target_id: Mapped[str] # Polymorphic association or generic
    summary: Mapped[str]
```
