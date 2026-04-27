"""Dashboard routes — HTML pages and API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from src.dashboard.app import templates
from src.db import repository

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, topic: str | None = Query(None)):
    """Main dashboard page with overview stats."""
    stats = await repository.get_content_stats(topic=topic)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "stats": stats,
            "topic": topic,
            "now": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        },
    )


@router.get("/content", response_class=HTMLResponse)
async def content_list(
    request: Request,
    page: int = Query(1, ge=1),
    status: str | None = Query(None),
    category: str | None = Query(None),
    topic: str | None = Query(None),
):
    """Content list page with filtering."""
    per_page = 25
    offset = (page - 1) * per_page
    items, total = await repository.get_all_content(
        limit=per_page, offset=offset, status=status, category=category, topic=topic
    )
    total_pages = (total + per_page - 1) // per_page

    return templates.TemplateResponse(
        "content.html",
        {
            "request": request,
            "items": items,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "status_filter": status,
            "category_filter": category,
            "topic_filter": topic,
        },
    )


@router.get("/api/stats")
async def api_stats(topic: str | None = Query(None)):
    """JSON API endpoint for dashboard stats (used by htmx polling)."""
    return await repository.get_content_stats(topic=topic)


@router.get("/api/content")
async def api_content(
    page: int = Query(1, ge=1),
    status: str | None = Query(None),
    category: str | None = Query(None),
    topic: str | None = Query(None),
):
    """JSON API endpoint for content list."""
    per_page = 25
    offset = (page - 1) * per_page
    items, total = await repository.get_all_content(
        limit=per_page, offset=offset, status=status, category=category, topic=topic
    )
    return {"items": items, "total": total, "page": page}


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}
