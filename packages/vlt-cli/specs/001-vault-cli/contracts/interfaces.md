# Core Interfaces

## IVaultService (Core Logic)
The main entry point for CLI commands.

```python
class IVaultService(ABC):
    @abstractmethod
    def create_project(self, name: str, description: str) -> Project: ...
    
    @abstractmethod
    def create_thread(self, project_id: str, name: str, initial_thought: str) -> Thread: ...
    
    @abstractmethod
    def add_thought(self, thread_id: str, content: str) -> Node: ...
    
    @abstractmethod
    def get_thread_state(self, thread_id: str) -> ThreadStateView: ...
    
    @abstractmethod
    def get_project_overview(self, project_id: str) -> ProjectOverviewView: ...
    
    @abstractmethod
    def search(self, query: str, project_id: Optional[str] = None) -> List[SearchResult]: ...
```

## ILibrarian (Background Service)
The interface for the background processor.

```python
class ILibrarian(ABC):
    @abstractmethod
    def process_pending_nodes(self) -> int:
        """Processes un-summarized nodes. Returns count of processed nodes."""
        ...
        
    @abstractmethod
    def update_project_overviews(self) -> int:
        """Updates stale project summaries."""
        ...
```

## ILLMProvider (Adapter)
Interface for the LLM backend.

```python
class ILLMProvider(ABC):
    @abstractmethod
    def generate_summary(self, context: str, new_content: str) -> str: ...
    
    @abstractmethod
    def get_embedding(self, text: str) -> List[float]: ...
```
