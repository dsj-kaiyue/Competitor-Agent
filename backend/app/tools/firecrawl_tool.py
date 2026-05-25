from typing import Any

from app.core.config import settings


class FirecrawlTool:
    def __init__(self) -> None:
        self.api_key = settings.firecrawl_api_key

    def search(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        if not self.api_key:
            return []
        try:
            from firecrawl import V1FirecrawlApp

            app = V1FirecrawlApp(api_key=self.api_key)
            result = app.search(query=query, limit=max_results)
            data = getattr(result, "data", None)
            if data is None and isinstance(result, dict):
                data = result.get("data", [])
            return [dict(item) for item in (data or [])]
        except Exception:
            return []

    def scrape(self, url: str) -> dict[str, Any] | None:
        if not self.api_key:
            return None
        try:
            from firecrawl import V1FirecrawlApp

            app = V1FirecrawlApp(api_key=self.api_key)
            result = app.scrape_url(url, formats=["markdown"], only_main_content=True, timeout=30000)
            if not getattr(result, "success", False):
                return None
            metadata = getattr(result, "metadata", None) or {}
            return {
                "markdown": getattr(result, "markdown", None) or "",
                "html": getattr(result, "html", None),
                "metadata": metadata,
                "title": metadata.get("title") if isinstance(metadata, dict) else None,
            }
        except Exception:
            return None
