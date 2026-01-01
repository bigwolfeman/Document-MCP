from abc import ABC, abstractmethod
from typing import List, Optional, Any
from pydantic import BaseModel
from datetime import datetime

# Views / Pydantic Models for Interfaces
class NodeView(BaseModel):
    id: str
    content: str
    author: str
    timestamp: datetime
    sequence_id: int

class ThreadStateView(BaseModel):
    thread_id: str
    project_id: str
    summary: str
    recent_nodes: List[NodeView]
    meta: dict

class ProjectOverviewView(BaseModel):
    project_id: str
    summary: str
    active_threads: List[dict] # {id, status, last_activity}

class SearchResult(BaseModel):
    node_id: str
    content: str
    score: float
    thread_id: str

# Abstract Interfaces
class IVaultService(ABC):
    @abstractmethod
    def create_project(self, name: str, description: str) -> Any: ...
    
    @abstractmethod
    def create_thread(self, project_id: str, name: str, initial_thought: str, author: str = "user") -> Any: ...
    
    @abstractmethod
    def add_thought(self, thread_id: str, content: str, author: str = "user") -> Any: ...
    
    @abstractmethod
    def get_thread_state(self, thread_id: str, limit: int = 5) -> ThreadStateView: ...
    
    @abstractmethod
    def search_thread(self, thread_id: str, query: str) -> List[SearchResult]: ...
    
    @abstractmethod
    def get_project_overview(self, project_id: str) -> ProjectOverviewView: ...
    
    @abstractmethod
    def search(self, query: str, project_id: Optional[str] = None) -> List[SearchResult]: ...

    @abstractmethod
    def add_tag(self, node_id: str, tag_name: str) -> Any: ...

    @abstractmethod
    def add_reference(self, source_node_id: str, target_thread_id: str, note: str) -> Any: ...

    @abstractmethod
    def move_thread(self, thread_id: str, new_project_id: str) -> Any: ...

class ILibrarian(ABC):
    @abstractmethod
    def process_pending_nodes(self) -> int:
        """Processes un-summarized nodes. Returns count of processed nodes."""
        ...
        
    @abstractmethod
    def update_project_overviews(self) -> int:
        """Updates stale project summaries."""
        ...

class ILLMProvider(ABC):
    @abstractmethod
    def generate_summary(self, context: str, new_content: str) -> str: ...
    
    @abstractmethod
    def get_embedding(self, text: str) -> List[float]: ...
