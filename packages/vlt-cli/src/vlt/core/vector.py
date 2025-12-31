import numpy as np
import pickle
from typing import List, Tuple

class VectorService:
    @staticmethod
    def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(v1, v2) / (norm1 * norm2))

    @staticmethod
    def serialize(vector: List[float]) -> bytes:
        return pickle.dumps(np.array(vector, dtype=np.float32))

    @staticmethod
    def deserialize(data: bytes) -> np.ndarray:
        return pickle.loads(data)

    def search_memory(self, query_vec: List[float], candidates: List[Tuple[str, bytes]], top_k: int = 5) -> List[Tuple[str, float]]:
        """
        candidates: List of (id, serialized_vector)
        Returns: List of (id, score)
        """
        q = np.array(query_vec, dtype=np.float32)
        results = []
        
        for doc_id, blob in candidates:
            if not blob:
                continue
            doc_vec = self.deserialize(blob)
            score = self.cosine_similarity(q, doc_vec)
            results.append((doc_id, score))
            
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
