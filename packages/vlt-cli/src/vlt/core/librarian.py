import uuid
from typing import List
from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session
from vlt.core.interfaces import ILibrarian, ILLMProvider
from vlt.core.models import Node, State, Thread, Project
from vlt.core.vector import VectorService
from vlt.db import get_db

class Librarian(ILibrarian):
    def __init__(self, llm_provider: ILLMProvider, db: Session = None):
        self.llm = llm_provider
        self._db = db

    @property
    def db(self) -> Session:
        if self._db is None:
            self._db = next(get_db())
        return self._db

    def process_pending_nodes(self) -> int:
        """
        Finds threads with new nodes that are NOT covered by the current State.
        Updates the State for those threads.
        """
        processed_count = 0
        
        # 1. Get all threads
        threads = self.db.scalars(select(Thread)).all()
        
        for thread in threads:
            # Get current state
            state = self.db.scalars(
                select(State)
                .where(State.target_id == thread.id)
                .where(State.target_type == "thread")
            ).first()
            
            last_head_id = state.head_node_id if state else None
            
            # Find nodes AFTER the last head
            query = select(Node).where(Node.thread_id == thread.id).order_by(Node.sequence_id)
            if last_head_id:
                head_node = self.db.get(Node, last_head_id)
                if head_node:
                    query = query.where(Node.sequence_id > head_node.sequence_id)
            
            new_nodes = self.db.scalars(query).all()
            
            if not new_nodes:
                continue
                
            # Collapse new nodes content
            new_content = "\n".join([f"- {n.content}" for n in new_nodes])
            current_summary = state.summary if state else "No history."
            
            # Generate new summary
            updated_summary = self.llm.generate_summary(current_summary, new_content)
            
            # Embed NEW nodes
            for node in new_nodes:
                if not node.embedding:
                    # Note: We should ideally batch this
                    emb = self.llm.get_embedding(node.content)
                    node.embedding = VectorService.serialize(emb)

            # Update State
            if not state:
                state = State(
                    id=str(uuid.uuid4()),
                    target_id=thread.id,
                    target_type="thread",
                    summary=updated_summary,
                    head_node_id=new_nodes[-1].id
                )
                self.db.add(state)
            else:
                state.summary = updated_summary
                state.head_node_id = new_nodes[-1].id
            
            processed_count += len(new_nodes)
            
        self.db.commit()
        return processed_count

    def update_project_overviews(self) -> int:
        """
        Aggregates thread summaries into project summaries.
        """
        updated_count = 0
        projects = self.db.scalars(select(Project)).all()
        
        for project in projects:
            # Get all thread summaries
            thread_states = self.db.scalars(
                select(State)
                .join(Thread, Thread.id == State.target_id)
                .where(Thread.project_id == project.id)
                .where(State.target_type == "thread")
            ).all()
            
            if not thread_states:
                continue
                
            combined_context = "\n\n".join([f"Thread {s.target_id}:\n{s.summary}" for s in thread_states])
            
            # Get current project state
            proj_state = self.db.scalars(
                select(State)
                .where(State.target_id == project.id)
                .where(State.target_type == "project")
            ).first()
            
            current_summary = proj_state.summary if proj_state else "New Project."
            
            # Generate Overview
            new_summary = self.llm.generate_summary(current_summary, combined_context)
             
            if not proj_state:
                proj_state = State(
                    id=str(uuid.uuid4()),
                    target_id=project.id,
                    target_type="project",
                    summary=new_summary
                )
                self.db.add(proj_state)
            else:
                proj_state.summary = new_summary
                
            updated_count += 1
            
        self.db.commit()
        return updated_count