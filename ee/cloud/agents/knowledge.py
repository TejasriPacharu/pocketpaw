"""Agent knowledge ingestion — text, URLs, PDFs, and images into per-agent ChromaDB collections.

Each agent gets its own Chroma collection: agent_{agent_id}
Documents are chunked and embedded for RAG retrieval during conversations.

Supports:
- Plain text
- URLs (HTML → text extraction)
- PDFs (text extraction via pypdf or pdfplumber)
- Images (OCR via pytesseract or description via LLM)
- Common docs (.txt, .md, .csv, .json)
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
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
        """Get or create a ChromaDB collection for an agent, using configured embeddings."""
        from pocketpaw.vectordb.chroma_adapter import ChromaAdapter
        from pocketpaw.config import Settings

        settings = Settings.load()
        return ChromaAdapter(
            collection_name=f"agent_{agent_id}",
            embedding_provider=getattr(settings, "vectordb_embedding_provider", "default"),
            embedding_model=getattr(settings, "vectordb_embedding_model", "all-MiniLM-L6-v2"),
        )

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
    async def ingest_pdf(agent_id: str, file_path: str) -> dict:
        """Extract text from PDF and ingest."""
        path = Path(file_path)
        if not path.exists():
            return {"error": f"File not found: {file_path}"}

        text = ""
        # Try pypdf first (lighter), fall back to pdfplumber (handles tables better)
        try:
            import pypdf

            reader = pypdf.PdfReader(str(path))
            pages = []
            for page in reader.pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    pages.append(page_text)
            text = "\n\n".join(pages)
        except ImportError:
            try:
                import pdfplumber

                with pdfplumber.open(str(path)) as pdf:
                    pages = []
                    for page in pdf.pages:
                        page_text = page.extract_text() or ""
                        if page_text.strip():
                            pages.append(page_text)
                    text = "\n\n".join(pages)
            except ImportError:
                return {"error": "Install pypdf or pdfplumber for PDF support: pip install pypdf"}

        if not text.strip():
            return {"error": "No text extracted from PDF", "file": path.name}

        result = await KnowledgeService.ingest_text(agent_id, text, source=f"pdf:{path.name}")
        result["file"] = path.name
        result["pages"] = len(text.split("\n\n"))
        return result

    @staticmethod
    async def ingest_image(agent_id: str, file_path: str) -> dict:
        """Extract text from image via OCR and ingest."""
        path = Path(file_path)
        if not path.exists():
            return {"error": f"File not found: {file_path}"}

        text = ""
        try:
            from PIL import Image
            import pytesseract

            img = Image.open(str(path))
            text = pytesseract.image_to_string(img)
        except ImportError:
            return {"error": "Install Pillow and pytesseract for image OCR: pip install Pillow pytesseract"}

        if not text.strip():
            return {"error": "No text extracted from image", "file": path.name}

        result = await KnowledgeService.ingest_text(agent_id, text, source=f"image:{path.name}")
        result["file"] = path.name
        return result

    @staticmethod
    async def ingest_file(agent_id: str, file_path: str) -> dict:
        """Auto-detect file type and ingest accordingly."""
        path = Path(file_path)
        if not path.exists():
            return {"error": f"File not found: {file_path}"}

        suffix = path.suffix.lower()

        # PDF
        if suffix == ".pdf":
            return await KnowledgeService.ingest_pdf(agent_id, file_path)

        # Images
        if suffix in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"):
            return await KnowledgeService.ingest_image(agent_id, file_path)

        # Text-based files
        if suffix in (".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".html", ".xml", ".log"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                return {"error": f"Failed to read file: {exc}"}
            if not text.strip():
                return {"error": "File is empty", "file": path.name}
            result = await KnowledgeService.ingest_text(agent_id, text, source=f"file:{path.name}")
            result["file"] = path.name
            return result

        # Word documents
        if suffix == ".docx":
            try:
                import docx

                doc = docx.Document(str(path))
                text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
            except ImportError:
                return {"error": "Install python-docx for .docx support: pip install python-docx"}
            if not text.strip():
                return {"error": "No text extracted from document", "file": path.name}
            result = await KnowledgeService.ingest_text(agent_id, text, source=f"docx:{path.name}")
            result["file"] = path.name
            return result

        return {"error": f"Unsupported file type: {suffix}", "file": path.name}

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
