# Created: Knowledge base domain router for ee/cloud.
# Updated: 2026-04-06 — Switched from pocketpaw.knowledge to standalone
# knowledge_base package with PocketPawCompilerBackend adapter.
# Workspace-scoped KB endpoints: search, ingest (text/url), lint, article,
# concept, stats, list articles, list concepts.
"""Knowledge base domain — FastAPI router.

Workspace-scoped knowledge base endpoints consumed by the wiki pocket template
and other KB-aware UI components.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from ee.cloud.kb.schemas import IngestTextRequest, IngestUrlRequest, LintRequest, SearchRequest
from ee.cloud.license import require_license
from ee.cloud.shared.deps import current_user_id, current_workspace_id
from ee.cloud.shared.errors import CloudError, NotFound

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/kb", tags=["Knowledge Base"], dependencies=[Depends(require_license)]
)


def _engine(workspace_id: str, scope_override: str | None = None):
    """Build a KnowledgeEngine for the given workspace (or overridden scope)."""
    from knowledge_base import KnowledgeEngine
    from ee.cloud.kb.backend_adapter import PocketPawCompilerBackend

    scope = scope_override or f"workspace:{workspace_id}"
    return KnowledgeEngine(
        scope=scope,
        backend=PocketPawCompilerBackend(),
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@router.post("/search")
async def search_kb(
    body: SearchRequest,
    workspace_id: str = Depends(current_workspace_id),
    user_id: str = Depends(current_user_id),
) -> dict:
    """Search KB articles — returns metadata + snippet, not full content."""
    engine = _engine(workspace_id, body.scope)
    articles = await engine.search(body.query, body.limit)
    return {
        "results": [
            {
                **a.to_dict(),
                "snippet": (a.summary or a.content[:300]).strip(),
            }
            for a in articles
        ],
        "total": len(articles),
    }


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


@router.post("/ingest/text")
async def ingest_text(
    body: IngestTextRequest,
    workspace_id: str = Depends(current_workspace_id),
    user_id: str = Depends(current_user_id),
) -> dict:
    """Ingest plain text into the workspace knowledge base."""
    engine = _engine(workspace_id, body.scope)
    try:
        article = await engine.ingest_text(body.text, body.source)
        return {"article": article.to_dict(), "source": body.source}
    except Exception as exc:
        logger.error("KB text ingest failed: %s", exc, exc_info=True)
        raise CloudError(500, "kb.ingest_failed", str(exc)) from exc


@router.post("/ingest/url")
async def ingest_url(
    body: IngestUrlRequest,
    workspace_id: str = Depends(current_workspace_id),
    user_id: str = Depends(current_user_id),
) -> dict:
    """Fetch and ingest a URL into the workspace knowledge base."""
    engine = _engine(workspace_id, body.scope)
    try:
        article = await engine.ingest_url(body.url)
        return {"article": article.to_dict(), "url": body.url}
    except Exception as exc:
        logger.error("KB URL ingest failed: %s", exc, exc_info=True)
        raise CloudError(500, "kb.ingest_failed", str(exc)) from exc


# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------


@router.post("/lint")
async def lint_kb(
    body: LintRequest,
    workspace_id: str = Depends(current_workspace_id),
    user_id: str = Depends(current_user_id),
) -> dict:
    """Run LLM-powered health checks on the knowledge base."""
    engine = _engine(workspace_id, body.scope)
    issues = await engine.lint()
    return {"issues": [i.to_dict() for i in issues], "total": len(issues)}


# ---------------------------------------------------------------------------
# Browse — single article / concept
# ---------------------------------------------------------------------------


@router.get("/article/{article_id}")
async def get_article(
    article_id: str,
    workspace_id: str = Depends(current_workspace_id),
    user_id: str = Depends(current_user_id),
) -> dict:
    """Get a full article by ID (includes content)."""
    engine = _engine(workspace_id)
    article = engine.get_article(article_id)
    if not article:
        raise NotFound("article", article_id)
    return {
        **article.to_dict(),
        "content": article.content,
    }


@router.get("/concept/{name}")
async def get_concept_articles(
    name: str,
    workspace_id: str = Depends(current_workspace_id),
    user_id: str = Depends(current_user_id),
) -> dict:
    """Get all articles associated with a concept."""
    engine = _engine(workspace_id)
    articles = engine.articles_by_concept(name)
    return {
        "concept": name,
        "articles": [a.to_dict() for a in articles],
        "total": len(articles),
    }


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@router.get("/stats")
async def kb_stats(
    workspace_id: str = Depends(current_workspace_id),
    user_id: str = Depends(current_user_id),
) -> dict:
    """Get knowledge base statistics."""
    engine = _engine(workspace_id)
    return engine.stats()


# ---------------------------------------------------------------------------
# List all — for first load
# ---------------------------------------------------------------------------


@router.get("/articles")
async def list_articles(
    workspace_id: str = Depends(current_workspace_id),
    user_id: str = Depends(current_user_id),
) -> dict:
    """List all articles (metadata only, no full content)."""
    engine = _engine(workspace_id)
    articles = engine.list_articles()
    return {"articles": articles, "total": len(articles)}


@router.get("/concepts")
async def list_concepts(
    workspace_id: str = Depends(current_workspace_id),
    user_id: str = Depends(current_user_id),
) -> dict:
    """List all concepts with their article associations."""
    engine = _engine(workspace_id)
    concepts = engine.list_concepts()
    return {"concepts": concepts, "total": len(concepts)}
