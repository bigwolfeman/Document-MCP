#!/usr/bin/env python3
"""
Quick test script for T021 and T022 implementations.
Tests embedding client and BM25 indexer functionality.
"""

import asyncio
from vlt.core.coderag import (
    get_embedding,
    get_embeddings_batch,
    BM25Indexer,
)
from vlt.config import Settings


async def test_embeddings():
    """Test embedding client."""
    print("\n=== Testing Embedding Client (T021) ===")

    settings = Settings()

    # Test 1: Check if API key is configured
    if not settings.openrouter_api_key:
        print("⚠ No API key configured - embeddings will return None (expected)")
        result = await get_embedding("test text")
        assert result is None, "Should return None when no API key"
        print("✓ Graceful degradation works (no API key)")
        return
    else:
        print(f"✓ API key configured")
        print(f"✓ Using model: {settings.openrouter_embedding_model}")

    # Test 2: Single embedding
    print("\nTest: Single embedding...")
    text = "def authenticate_user(username: str, password: str) -> bool:"
    embedding = await get_embedding(text, settings)

    if embedding is None:
        print("✗ Failed to generate embedding")
        return
    else:
        print(f"✓ Generated embedding with {len(embedding)} dimensions")
        assert isinstance(embedding, list), "Embedding should be a list"
        assert all(isinstance(x, float) for x in embedding), "All values should be floats"
        print(f"  Sample values: {embedding[:5]}")

    # Test 3: Batch embeddings
    print("\nTest: Batch embeddings...")
    texts = [
        "class UserService:",
        "def login(user: User) -> Token:",
        "async def fetch_data() -> Dict:",
        "import logging",
        "# This is a comment",
    ]

    embeddings = await get_embeddings_batch(texts, batch_size=3, settings=settings)

    print(f"✓ Generated {len(embeddings)} embeddings")
    successful = sum(1 for e in embeddings if e is not None)
    print(f"  Successful: {successful}/{len(embeddings)}")

    for i, emb in enumerate(embeddings):
        if emb:
            print(f"  Text {i}: {len(emb)} dims")


def test_bm25():
    """Test BM25 indexer."""
    print("\n=== Testing BM25 Indexer (T022) ===")

    with BM25Indexer() as indexer:
        # Test 1: Get initial stats
        print("\nTest: Index stats...")
        stats = indexer.get_stats()
        print(f"✓ Index stats: {stats}")

        # Test 2: Index some test chunks
        print("\nTest: Indexing chunks...")
        test_chunks = [
            {
                "chunk_id": "test-chunk-1",
                "name": "authenticate_user",
                "qualified_name": "auth.service.authenticate_user",
                "signature": "def authenticate_user(username: str, password: str) -> bool",
                "docstring": "Authenticate a user with username and password",
                "body": "def authenticate_user(username: str, password: str) -> bool:\n    return check_credentials(username, password)"
            },
            {
                "chunk_id": "test-chunk-2",
                "name": "UserService",
                "qualified_name": "auth.UserService",
                "signature": "class UserService",
                "docstring": "Service for managing user authentication and authorization",
                "body": "class UserService:\n    def __init__(self):\n        self.auth_provider = AuthProvider()"
            },
            {
                "chunk_id": "test-chunk-3",
                "name": "login",
                "qualified_name": "api.routes.login",
                "signature": "async def login(request: Request) -> Response",
                "docstring": "Handle user login requests",
                "body": "async def login(request: Request) -> Response:\n    data = await request.json()\n    return authenticate_user(data['username'], data['password'])"
            },
        ]

        for chunk in test_chunks:
            indexer.index_chunk(**chunk)
        print(f"✓ Indexed {len(test_chunks)} test chunks")

        # Test 3: Search for exact match
        print("\nTest: BM25 search (exact match)...")
        results = indexer.search_bm25("authenticate_user", limit=5)
        print(f"✓ Found {len(results)} results for 'authenticate_user'")
        for chunk_id, score in results[:3]:
            print(f"  {chunk_id}: score={score:.2f}")

        # Test 4: Search for concept
        print("\nTest: BM25 search (concept)...")
        results = indexer.search_bm25("user login authentication", limit=5)
        print(f"✓ Found {len(results)} results for 'user login authentication'")
        for chunk_id, score in results[:3]:
            print(f"  {chunk_id}: score={score:.2f}")

        # Test 5: Search with special characters
        print("\nTest: BM25 search (special chars)...")
        results = indexer.search_bm25("authenticate_user()", limit=5)
        print(f"✓ Found {len(results)} results for 'authenticate_user()' (sanitized)")

        # Test 6: Delete chunk
        print("\nTest: Delete chunk...")
        indexer.delete_chunk("test-chunk-1")
        results = indexer.search_bm25("authenticate_user", limit=5)
        print(f"✓ After deletion: {len(results)} results")

        # Cleanup
        print("\nTest: Cleanup...")
        for chunk in test_chunks:
            indexer.delete_chunk(chunk["chunk_id"])
        print("✓ Cleaned up test chunks")


async def main():
    """Run all tests."""
    print("=" * 60)
    print("CodeRAG Component Tests (T021 + T022)")
    print("=" * 60)

    # Test embeddings
    await test_embeddings()

    # Test BM25
    test_bm25()

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
