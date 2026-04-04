"""Agent knowledge ingestion — text, URLs, and files into per-agent ChromaDB collections.

Each agent gets its own Chroma collection: agent_{agent_id}
Documents are chunked and embedded for RAG retrieval during conversations.
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Chunk settings
CHUNK_SIZE = 1000  # chars per chunk
CHUNK_OVERLAP = 200


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start += chunk_size - overlap
    return chunks


def _doc_id(agent_id: str, source: str, index: int) -> str:
    """Generate a deterministic doc ID from agent + source + chunk index."""
    h = hashlib.md5(f"{agent_id}:{source}".encode()).hexdigest()[:12]
    return f"{h}_{index}"


class KnowledgeService:
    """Manages per-agent knowledge bases via ChromaDB."""

    @staticmethod
    def _get_store(agent_id: str):
        """Get or create a ChromaDB collection for an agent."""
        from pocketpaw.vectordb.chroma_adapter import ChromaAdapter
        return ChromaAdapter(collection_name=f"agent_{agent_id}")

    @staticmethod
    async def ingest_text(agent_id: str, text: str, source: str = "manual") -> dict:
        """Chunk and index plain text."""
        store = KnowledgeService._get_store(agent_id)
        chunks = _chunk_text(text)
        for i, chunk in enumerate(chunks):
            doc_id = _doc_id(agent_id, source, i)
            await store.add(doc_id, chunk, metadata={"source": source, "chunk": i})
        logger.info("Ingested %d chunks for agent %s from %s", len(chunks), agent_id, source)
        return {"chunks": len(chunks), "source": source}

    @staticmethod
    async def ingest_url(agent_id: str, url: str) -> dict:
        """Fetch URL content, chunk, and index."""
        import httpx

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content = resp.text
        except Exception as exc:
            logger.warning("Failed to fetch URL %s: %s", url, exc)
            return {"error": f"Failed to fetch: {exc}", "url": url}

        # Strip HTML tags for basic text extraction
        clean = re.sub(r"<[^>]+>", " ", content)
        clean = re.sub(r"\s+", " ", clean).strip()

        if not clean:
            return {"error": "No text content extracted", "url": url}

        # Truncate very large pages
        clean = clean[:100_000]

        result = await KnowledgeService.ingest_text(agent_id, clean, source=url)
        result["url"] = url
        return result

    @staticmethod
    async def search(agent_id: str, query: str, limit: int = 5) -> list[str]:
        """Search an agent's knowledge base."""
        store = KnowledgeService._get_store(agent_id)
        return await store.search(query, limit=limit)

    @staticmethod
    async def clear(agent_id: str) -> dict:
        """Delete all knowledge for an agent."""
        try:
            from pocketpaw.vectordb.chroma_adapter import ChromaAdapter
            import chromadb

            adapter = ChromaAdapter(collection_name=f"agent_{agent_id}")
            # Delete the collection entirely
            adapter.client.delete_collection(f"agent_{agent_id}")
            logger.info("Cleared knowledge for agent %s", agent_id)
            return {"ok": True}
        except Exception as exc:
            logger.warning("Failed to clear knowledge for agent %s: %s", agent_id, exc)
            return {"ok": False, "error": str(exc)}
